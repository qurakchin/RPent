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

"""Map changed paths to the components, tests and environments they can affect.

`fast ci` narrows which tests a pull request runs and `full ci` narrows which
environments it installs from the same answer, so the two levels cannot drift: a
path under a component directory names that component; the affected
environments are the ones whose resolution closure contains it, and the
affected tests are the suites that mirror it.

A path outside every component directory belongs to the core or the installer,
so it can change every installation. An unknown component name is treated the
same way rather than silently ignored. The answer then names every component,
every environment, and the whole unit suite. When no path is given there is
nothing to narrow the answer with, so the same happens.

Changes confined to the repository's install data are narrower: they decide
which environment can be built rather than how a component behaves, so they
select the repository contract tests and the environments that read the changed
files. Unrecognised install data widens back to every environment.

Cross-component contracts under ``tests/unit_tests/contracts/`` import only the
core and ``infra-dev`` dependencies. A change confined to that directory runs
the group without installing an environment, and a change to a component the
contracts cover reruns the group as well.

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

from rpent.install.discovery import (
    Catalog,
    discover,
    environment_names,
    requested_components,
)
from rpent.install.resolve import resolve
from tests.tooling.matrix import MATRICES

#: Component owner directories, longest prefix first.
COMPONENT_ROOTS = (
    ("components/models", "model"),
    ("components/sim", "sim"),
    ("components/tools", "tool"),
    ("components/infra", "infra"),
    ("robots", "robot"),
)
#: Tests every component group contributes to, relative to the repository root.
SHARED_TESTS = ("tests/unit_tests/conftest.py",)
#: Robot toolkits are exercised once per slice, so a slice change reruns them.
ROBOT_SHARED_TESTS = (
    "tests/unit_tests/robots/test_tool_schema_contracts.py",
    "tests/unit_tests/robots/test_toolkit_contracts.py",
)
#: Simulator components are exercised through the robot slice that wires them.
#: LIBERO-plus adds task definitions on top of the LIBERO simulator, so the
#: LIBERO slice covers it.
SIM_ROBOT_SLICES = {"libero_plus": "libero"}
#: Test directories for component kinds whose directory name is not the kind.
COMPONENT_TEST_DIRS = {"tool": "tools"}
#: Environments a pull request installs when a change affects the core. They
#: cover the core-only environment and the CPU test environment without pulling
#: the full GPU matrix into every core edit; nightly and release runs still
#: install every environment.
PR_PILOT_TARGETS = ("minimal", "robot-robotwin", "infra-unit_cpu")
#: Paths whose change can alter every installation, so a PR installs every
#: environment instead of the pilot set. Install data changes narrow their own
#: environment set first; a path here in a mixed change still widens it. Packaging
#: files outside ``rpent/`` and ``tests/`` already select every environment
#: because no other path rule matches them.
PR_ALL_TARGET_PREFIXES = (
    "rpent/install/",
    "tests/tooling/",
    ".github/",
)
#: The repository's install data: the component manifests, locks and packaging
#: settings that decide what each environment contains. A manifest change
#: narrows to the environment its component names, and a lock narrows to the
#: environment it was compiled for.
INSTALL_DATA_PREFIXES = ("tests/locks/",)
INSTALL_DATA_ROOT_FILES = ("pyproject.toml",)
#: Repository contract tests read that data. Installer unit tests live under
#: ``tests/unit_tests/rpent/install/`` and use synthetic manifests, so the two
#: groups stay distinguishable by path.
INSTALL_DATA_TESTS = "tests/unit_tests/installs"
#: Cross-component contract tests that import only the core and ``infra-dev``
#: dependencies. They mirror data owned by more than one component, so a change
#: to either side reruns the group.
CROSS_COMPONENT_TESTS = "tests/unit_tests/contracts"


@dataclass(frozen=True)
class Scope:
    """What a change can affect, in the form CI jobs consume.

    ``targets`` keeps its historical name: the workflow reads it as the
    environments to install, and every entry is an environment name.
    """

    components: tuple[str, ...]
    tests: tuple[str, ...]
    targets: tuple[str, ...]
    #: True when nothing narrowed the answer to part of the repository.
    full: bool
    #: Environments a pull request installs. For a component change this equals
    #: ``targets``; for a core change it is the pilot set, while ``targets``
    #: stays complete for nightly and release runs. Installer and manifest
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


def _component_for(path: str) -> str | None:
    """Return the component name when ``path`` belongs to one component.

    A component is named ``<kind>-<directory>``, so the owning directory and
    the kind together name it without reading the manifest.
    """
    parts = path.split("/")
    for root, kind in COMPONENT_ROOTS:
        root_parts = root.split("/")
        if parts[: len(root_parts)] == root_parts and len(parts) > len(root_parts):
            return f"{kind}-{parts[len(root_parts)]}"
    return None


def _is_install_data(path: str) -> bool:
    """Return whether ``path`` changes the repository's install data."""
    if path in INSTALL_DATA_ROOT_FILES:
        return True
    if path.endswith("/component.toml") or path == "component.toml":
        return True
    if path.startswith(INSTALL_DATA_PREFIXES):
        return True
    return path == INSTALL_DATA_TESTS or path.startswith(f"{INSTALL_DATA_TESTS}/")


def _targets_for_install_data(paths: list[str], catalog: Catalog) -> tuple[str, ...]:
    """Return the environments whose installation reads ``paths``, or all of them.

    A component manifest names the environment its component installs under and
    a lock names the environment it was compiled for. Packaging settings feed
    every environment, and an unrecognised file widens the answer rather than
    guessing which environments it reaches.
    """
    every = environment_names(catalog.components)
    selected: set[str] = set()
    for path in paths:
        if path in INSTALL_DATA_ROOT_FILES:
            return every
        if path == INSTALL_DATA_TESTS or path.startswith(f"{INSTALL_DATA_TESTS}/"):
            # A test-only change installs nothing; the unit job still runs it.
            continue
        if path.endswith("/component.toml"):
            name = _component_for(path)
            if name is None or name not in catalog.components:
                return every
            selected.add(name)
            continue
        parts = path.split("/")
        area = parts[1] if len(parts) > 1 else ""
        stem = parts[2] if len(parts) > 2 else ""
        suffix = Path(stem).suffix
        if area == "locks" and suffix == ".lock" and len(parts) == 3:
            name = stem[: -len(suffix)]
            if name not in every:
                return every
            selected.add(name)
        else:
            return every
    return tuple(sorted(selected))


def _pr_targets(paths: list[str], environments: tuple[str, ...]) -> tuple[str, ...]:
    """Return the environments a pull request should install for ``paths``.

    A component change never reaches this helper: its environment set is already
    the resolution closure. For a core change, installing every GPU environment
    proves little beyond what nightly proves and costs a self-hosted runner
    slot, so the PR installs the core-only and CPU test environments. The
    installer, workflows, packaging, and a mixed change that still names one of
    them keep the full set; install data on its own narrows before this helper
    runs.
    """
    available = tuple(sorted(environments))
    if not paths:
        return available
    if any(path.startswith(PR_ALL_TARGET_PREFIXES) for path in paths):
        return available
    if all(path.startswith(("rpent/", "tests/")) for path in paths):
        pilots = tuple(name for name in PR_PILOT_TARGETS if name in environments)
        return pilots or available
    return available


def affected_components(paths: list[str], catalog: Catalog) -> set[str] | None:
    """Return the components ``paths`` touch, or ``None`` when all can change.

    ``None`` means the change is not confined to a known component: the core,
    the installer, install data, a lock, or an unowned path.
    """
    names: set[str] = set()
    for path in paths:
        name = _component_for(path)
        if name is None or name not in catalog.components:
            return None
        names.add(name)
    return names


def _tests_for(kind: str, name: str, root: Path) -> list[str]:
    """Return the existing test paths that mirror one component."""
    # A component is named ``<kind>-<directory>``; the tests mirror the
    # directory under the kind's test root. Simulator code is also exercised by
    # the robot slice that wires it.
    directory = name.partition("-")[2]
    if kind == "robot":
        candidates = [
            f"tests/unit_tests/robots/{directory}",
            *ROBOT_SHARED_TESTS,
            CROSS_COMPONENT_TESTS,
        ]
    elif kind == "model":
        candidates = [
            "tests/unit_tests/components/models",
            CROSS_COMPONENT_TESTS,
        ]
    elif kind == "sim":
        robot = SIM_ROBOT_SLICES.get(directory, directory)
        candidates = [
            f"tests/unit_tests/components/sim/{directory}",
            f"tests/unit_tests/robots/{robot}",
            *ROBOT_SHARED_TESTS,
            CROSS_COMPONENT_TESTS,
        ]
    else:
        test_dir = COMPONENT_TEST_DIRS.get(kind, kind)
        candidates = [
            f"tests/unit_tests/components/{test_dir}/{directory}",
            CROSS_COMPONENT_TESTS,
        ]
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
        targets = _targets_for_install_data(paths, catalog)
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
        # the `infra-dev` environment, which provides everything these contracts import.
        return Scope(
            components=(),
            tests=(CROSS_COMPONENT_TESTS,),
            targets=(),
            full=False,
        )
    names = affected_components(paths, catalog)
    if names is None or not paths:
        environments = environment_names(catalog.components)
        return Scope(
            components=tuple(sorted(catalog.components)),
            tests=("tests/unit_tests",),
            targets=environments,
            full=True,
            pr_targets=_pr_targets(paths, environments),
        )
    kinds = {name: catalog.components[name].kind for name in sorted(names)}
    tests: set[str] = {path for path in SHARED_TESTS if (root / path).exists()}
    for name, kind in kinds.items():
        tests.update(_tests_for(kind, name, root))
    targets: list[str] = []
    for name in environment_names(catalog.components):
        resolution = resolve(requested_components(name, catalog.components), catalog)
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
    """Return the environments whose closure contains what ``paths`` changed."""
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
