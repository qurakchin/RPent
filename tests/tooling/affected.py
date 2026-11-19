# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Map changed paths to the components, tests and targets they can affect.

`fast ci` narrows which tests a pull request runs and `full ci` narrows which
targets it installs from the same answer, so the two levels cannot drift: a
path under a component directory names that component; the affected targets
are the ones whose resolution closure contains it, and the affected tests are
the suites that mirror it.

A path outside every component directory belongs to the core, the installer, or
the target files themselves, so it can change every installation. An unknown
component name is treated the same way rather than silently ignored. The answer
then names every component, every target, and the whole unit suite. When no
path is given there is nothing to narrow the answer with, so the same happens.

Changes confined to the repository's install data are narrower: they decide
which environment can be built rather than how a component behaves, so they
select the repository contract tests and the targets that read the changed
files. Unrecognised install data widens back to every target.

Cross-component contracts under ``tests/unit_tests/contracts/`` import only the
core and ``dev`` dependencies. A change confined to that directory runs the
group without installing a target, and a change to a component the contracts
cover reruns the group as well.

Narrowing is fail-open throughout: a change no test directory covers, or a
component whose tests do not exist yet, widens the scope instead of reporting a
smaller one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallConfigError
from rpent.install.resolve import resolve
from tests.tooling.matrix import MATRICES

#: Component owner directories, longest prefix first.
COMPONENT_ROOTS = (
    ("components/models", "model"),
    ("components/toolkits", "toolkit"),
    ("robots", "robot"),
)
#: Tests every component group contributes to, relative to the repository root.
SHARED_TESTS = ("tests/unit_tests/conftest.py",)
#: Robot toolkits are exercised once per slice, so a slice change reruns them.
ROBOT_SHARED_TESTS = (
    "tests/unit_tests/robots/test_tool_schema_contracts.py",
    "tests/unit_tests/robots/test_toolkit_contracts.py",
)
#: Targets a pull request installs when a change affects the core. They cover
#: the core-only environment and the CPU toolkit without pulling the full GPU
#: matrix into every core edit; nightly and release runs still install every
#: target.
PR_PILOT_TARGETS = ("minimal", "robot-robotwin", "tool-geometry-eval")
#: Paths whose change can alter every installation, so a PR installs every
#: target instead of the pilot set. Install data changes narrow their own
#: target set first; a path here in a mixed change still widens it. Packaging
#: files outside ``rpent/`` and ``tests/`` already select every target because
#: no other path rule matches them.
PR_ALL_TARGET_PREFIXES = (
    "rpent/install/",
    "installs/",
    "tests/tooling/",
    ".github/",
)
#: The repository's install data: the target files, dependency-only manifests,
#: locks and packaging settings that decide what each environment contains.
#: User and test targets share the same discovery and schema, so a change under
#: either directory narrows to the target that reads it.
INSTALL_DATA_PREFIXES = ("installs/", "tests/targets/", "tests/locks/")
INSTALL_DATA_ROOT_FILES = ("pyproject.toml",)
#: Repository contract tests read that data. Installer unit tests live under
#: ``tests/unit_tests/rpent/install/`` and use synthetic manifests, so the two
#: groups stay distinguishable by path.
INSTALL_DATA_TESTS = "tests/unit_tests/installs"
#: Cross-component contract tests that import only the core and ``dev``
#: dependencies. They mirror data owned by more than one component, so a change
#: to either side reruns the group.
CROSS_COMPONENT_TESTS = "tests/unit_tests/contracts"


@dataclass(frozen=True)
class Scope:
    """What a change can affect, in the form CI jobs consume."""

    components: tuple[str, ...]
    tests: tuple[str, ...]
    targets: tuple[str, ...]
    #: True when nothing narrowed the answer to part of the repository.
    full: bool
    #: Targets a pull request installs. For a component change this equals
    #: ``targets``; for a core change it is the pilot set, while ``targets``
    #: stays complete for nightly and release runs. Installer and target
    #: changes keep the full set because they can alter any environment.
    pr_targets: tuple[str, ...] = ()
    #: True when every changed path is prose, so only the docs check applies.
    docs: bool = False

    def as_dict(self) -> dict[str, object]:
        """Return the JSON-ready form printed by the CLI."""
        return asdict(self)


def _is_docs(path: str) -> bool:
    """Return True when ``path`` only changes documentation."""
    return path.startswith("docs/") or path.endswith((".md", ".rst"))


def _component_for(path: str) -> tuple[str, str] | None:
    """Return ``(kind, name)`` when ``path`` belongs to one component."""
    parts = path.split("/")
    for root, kind in COMPONENT_ROOTS:
        root_parts = root.split("/")
        if parts[: len(root_parts)] == root_parts and len(parts) > len(root_parts):
            return kind, parts[len(root_parts)]
    return None


def _is_install_data(path: str) -> bool:
    """Return whether ``path`` changes the repository's install data."""
    if path in INSTALL_DATA_ROOT_FILES:
        return True
    if path.startswith(INSTALL_DATA_PREFIXES):
        return True
    return path == INSTALL_DATA_TESTS or path.startswith(f"{INSTALL_DATA_TESTS}/")


def _targets_requiring(name: str, catalog: Catalog) -> list[str] | None:
    """Return the targets that install deps component ``name``.

    ``None`` widens the answer when a target cannot be resolved: ``check``
    reports that target separately, and CI must install it rather than skip it.
    """
    if name not in catalog.components:
        return None
    found: list[str] = []
    for target_name, target in sorted(catalog.targets.items()):
        try:
            resolution = resolve(target, catalog)
        except InstallConfigError:
            return None
        if name in resolution.components:
            found.append(target_name)
    return found


def _targets_for_install_data(
    paths: list[str], catalog: Catalog, root: Path
) -> tuple[str, ...]:
    """Return the targets whose installation reads ``paths``, or all of them.

    A target file names itself, a lock names the target that declares it, and a
    deps manifest names the targets whose closure installs it. Packaging
    settings feed every target, and an unrecognised file widens the answer
    rather than guessing which environments it reaches.
    """
    every = tuple(sorted(catalog.targets))
    selected: set[str] = set()
    for path in paths:
        if path in INSTALL_DATA_ROOT_FILES:
            return every
        if path == INSTALL_DATA_TESTS or path.startswith(f"{INSTALL_DATA_TESTS}/"):
            # A test-only change installs nothing; the unit job still runs it.
            continue
        parts = path.split("/")
        area = parts[1] if len(parts) > 1 else ""
        stem = parts[2] if len(parts) > 2 else ""
        suffix = Path(stem).suffix
        if area == "targets" and suffix == ".toml" and len(parts) == 3:
            name = stem[: -len(suffix)]
            if name not in catalog.targets:
                return every
            selected.add(name)
        elif area == "locks" and suffix == ".lock" and len(parts) == 3:
            lock = (root / path).resolve()
            declared = [
                name
                for name, target in catalog.targets.items()
                if target.lock_file(root).resolve() == lock
            ]
            if not declared:
                return every
            selected.update(declared)
        elif area == "deps" and suffix == ".toml" and len(parts) == 3:
            required = _targets_requiring(stem[: -len(suffix)], catalog)
            if required is None:
                return every
            selected.update(required)
        else:
            return every
    return tuple(sorted(selected))


def _pr_targets(paths: list[str], targets: dict[str, object]) -> tuple[str, ...]:
    """Return the targets a pull request should install for ``paths``.

    A component change never reaches this helper: its target set is already the
    resolution closure. For a core change, installing every GPU target proves
    little beyond what nightly proves and costs a self-hosted runner slot, so
    the PR installs the core-only and CPU toolkit targets. The installer,
    workflows, packaging, and a mixed change that still names one of them keep
    the full set; install data on its own narrows before this helper runs.
    """
    available = tuple(sorted(targets))
    if not paths:
        return available
    if any(path.startswith(PR_ALL_TARGET_PREFIXES) for path in paths):
        return available
    if all(path.startswith(("rpent/", "tests/")) for path in paths):
        pilots = tuple(name for name in PR_PILOT_TARGETS if name in targets)
        return pilots or available
    return available


def affected_components(paths: list[str], catalog: Catalog) -> set[str] | None:
    """Return the components ``paths`` touch, or ``None`` when all can change.

    ``None`` means the change is not confined to a known component: the core,
    the installer, a target, a lock, or an unowned path.
    """
    names: set[str] = set()
    for path in paths:
        owner = _component_for(path)
        if owner is None:
            return None
        _, name = owner
        if name not in catalog.components:
            return None
        names.add(name)
    return names


def _tests_for(kind: str, name: str, root: Path) -> list[str]:
    """Return the existing test paths that mirror one component."""
    if kind == "robot":
        candidates = [
            f"tests/unit_tests/robots/{name}",
            *ROBOT_SHARED_TESTS,
            CROSS_COMPONENT_TESTS,
        ]
    elif kind == "model":
        candidates = [
            "tests/unit_tests/components/models",
            CROSS_COMPONENT_TESTS,
        ]
    else:
        candidates = ["tests/unit_tests/components/toolkits"]
    return [path for path in candidates if (root / path).exists()]


def affected_scope(paths: list[str], catalog: Catalog, root: Path) -> Scope:
    """Return the components, tests and targets ``paths`` can change."""
    if paths and all(_is_docs(path) for path in paths):
        return Scope(components=(), tests=(), targets=(), full=False, docs=True)
    if paths and all(_is_install_data(path) for path in paths):
        # Install data is repository-level: it changes which environment can be
        # built, not a component's behavior. The contract tests under
        # ``tests/unit_tests/installs/`` own the cross-file checks, and the
        # targets that read the changed files are the ones a pull request
        # installs.
        targets = _targets_for_install_data(paths, catalog, root)
        return Scope(
            components=(),
            tests=(INSTALL_DATA_TESTS,),
            targets=targets,
            full=False,
            pr_targets=targets,
        )
    if paths and all(
        path == CROSS_COMPONENT_TESTS or path.startswith(f"{CROSS_COMPONENT_TESTS}/")
        for path in paths
    ):
        # A test-only change installs nothing; the unit job runs the group in
        # the `dev` target, which provides everything these contracts import.
        return Scope(
            components=(),
            tests=(CROSS_COMPONENT_TESTS,),
            targets=(),
            full=False,
        )
    names = affected_components(paths, catalog)
    if names is None or not paths:
        return Scope(
            components=tuple(sorted(catalog.components)),
            tests=("tests/unit_tests",),
            targets=tuple(sorted(catalog.targets)),
            full=True,
            pr_targets=_pr_targets(paths, catalog.targets),
        )
    kinds = {name: catalog.components[name].kind for name in sorted(names)}
    tests: set[str] = {path for path in SHARED_TESTS if (root / path).exists()}
    for name, kind in kinds.items():
        tests.update(_tests_for(kind, name, root))
    targets: list[str] = []
    for name, target in sorted(catalog.targets.items()):
        try:
            resolution = resolve(target, catalog)
        except InstallConfigError:
            # An invalid target is a configuration error `check` reports;
            # installing it is the fastest way to surface it, so keep it.
            targets.append(name)
            continue
        if names & set(resolution.components):
            targets.append(name)
    if not tests:
        # A component with no tests yet must not shrink the suite to nothing.
        tests.add("tests/unit_tests")
    return Scope(
        components=tuple(kinds),
        tests=tuple(sorted(tests)),
        targets=tuple(targets),
        full=False,
        pr_targets=tuple(targets),
    )


def affected_targets(paths: list[str], catalog: Catalog, root: Path) -> tuple[str, ...]:
    """Return the targets whose closure contains what ``paths`` changed."""
    return affected_scope(paths, catalog, root).targets


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    """Return the repository-relative paths that differ between two refs."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", base, head],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git diff {base} {head} failed: {result.stderr.strip() or 'unknown error'}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None, *, root: Path) -> int:
    """Print the affected scope as a JSON object."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.tooling.affected",
        description="Map changed paths to affected components, tests and targets.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="changed paths; read from git when --base is given and none are "
        "passed; everything is affected when neither is given",
    )
    parser.add_argument("--base", help="git revision to diff from")
    parser.add_argument("--head", default="HEAD", help="git revision to diff to")
    parser.add_argument(
        "--runner",
        choices=sorted(MATRICES),
        help="restrict the targets to the ones one runner installs",
    )
    args = parser.parse_args(argv)
    if args.paths and args.base:
        parser.error("pass either changed paths or --base, not both")
    paths = args.paths or (
        changed_paths(root, args.base, args.head) if args.base else []
    )
    scope = affected_scope(paths, discover(root), root)
    if args.runner is not None:
        allowed = set(MATRICES[args.runner])
        scope = replace(
            scope,
            targets=tuple(name for name in scope.targets if name in allowed),
            pr_targets=tuple(name for name in scope.pr_targets if name in allowed),
        )
    print(json.dumps(scope.as_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(root=Path.cwd()))
