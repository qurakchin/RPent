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

"""Map changed paths to the components, tests and profiles they can affect.

`fast ci` narrows which tests a pull request runs and `full ci` narrows which
profiles it installs from the same answer, so the two levels cannot drift: a
path under a component directory names that component; the affected profiles
are the ones whose resolution closure contains it, and the affected tests are
the suites that mirror it.

A path outside every component directory belongs to the core, the installer, or
the profiles themselves, so it can change every installation. An unknown
component name is treated the same way rather than silently ignored. The answer
then names every component, every profile, and the whole unit suite. When no
path is given there is nothing to narrow the answer with, so the same happens.

Narrowing is fail-open throughout: a change no test directory covers, or a
component whose tests do not exist yet, widens the scope instead of reporting a
smaller one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallConfigError
from rpent.install.matrix import MATRICES
from rpent.install.resolve import resolve

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
#: Profiles a pull request installs when a change affects the core. They cover
#: the core-only environment and the CPU toolkit without pulling the full GPU
#: matrix into every core edit; nightly and release runs still install every
#: profile.
PR_PILOT_PROFILES = ("geometry-eval", "minimal")
#: Paths whose change can alter every installation, so a PR installs every
#: profile instead of the pilot set. Packaging files outside ``rpent/`` and
#: ``tests/`` already select every profile because no other path rule matches
#: them.
PR_ALL_PROFILE_PREFIXES = ("rpent/install/", "installs/", ".github/")


@dataclass(frozen=True)
class Scope:
    """What a change can affect, in the form CI jobs consume."""

    components: tuple[str, ...]
    tests: tuple[str, ...]
    profiles: tuple[str, ...]
    #: True when nothing narrowed the answer to part of the repository.
    full: bool
    #: Profiles a pull request installs. For a component change this equals
    #: ``profiles``; for a core change it is the pilot set, while ``profiles``
    #: stays complete for nightly and release runs. Installer and profile
    #: changes keep the full set because they can alter any environment.
    pr_profiles: tuple[str, ...] = ()
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


def _pr_profiles(paths: list[str], profiles: dict[str, object]) -> tuple[str, ...]:
    """Return the profiles a pull request should install for ``paths``.

    A component change never reaches this helper: its profile set is already
    the resolution closure. For a core change, installing every GPU profile
    proves little beyond what nightly proves and costs a self-hosted runner
    slot, so the PR installs the core-only and CPU toolkit profiles. Anything
    that can change an installation itself — the installer, profiles, locks,
    packaging, workflows — keeps the full set.
    """
    available = tuple(sorted(profiles))
    if not paths:
        return available
    if any(path.startswith(PR_ALL_PROFILE_PREFIXES) for path in paths):
        return available
    if all(path.startswith(("rpent/", "tests/")) for path in paths):
        pilots = tuple(name for name in PR_PILOT_PROFILES if name in profiles)
        return pilots or available
    return available


def affected_components(paths: list[str], catalog: Catalog) -> set[str] | None:
    """Return the components ``paths`` touch, or ``None`` when all can change.

    ``None`` means the change is not confined to a known component: the core,
    the installer, a profile, a lock, or an unowned path.
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
        ]
    elif kind == "model":
        candidates = ["tests/unit_tests/components/models"]
    else:
        candidates = ["tests/unit_tests/components/toolkits"]
    return [path for path in candidates if (root / path).exists()]


def affected_scope(paths: list[str], catalog: Catalog, root: Path) -> Scope:
    """Return the components, tests and profiles ``paths`` can change."""
    if paths and all(_is_docs(path) for path in paths):
        return Scope(components=(), tests=(), profiles=(), full=False, docs=True)
    names = affected_components(paths, catalog)
    if names is None or not paths:
        return Scope(
            components=tuple(sorted(catalog.components)),
            tests=("tests/unit_tests",),
            profiles=tuple(sorted(catalog.profiles)),
            full=True,
            pr_profiles=_pr_profiles(paths, catalog.profiles),
        )
    kinds = {name: catalog.components[name].kind for name in sorted(names)}
    tests: set[str] = {path for path in SHARED_TESTS if (root / path).exists()}
    for name, kind in kinds.items():
        tests.update(_tests_for(kind, name, root))
    profiles: list[str] = []
    for name, profile in sorted(catalog.profiles.items()):
        try:
            resolution = resolve(profile, catalog)
        except InstallConfigError:
            # An invalid profile is a configuration error `check` reports;
            # installing it is the fastest way to surface it, so keep it.
            profiles.append(name)
            continue
        if names & set(resolution.components):
            profiles.append(name)
    if not tests:
        # A component with no tests yet must not shrink the suite to nothing.
        tests.add("tests/unit_tests")
    return Scope(
        components=tuple(kinds),
        tests=tuple(sorted(tests)),
        profiles=tuple(profiles),
        full=False,
        pr_profiles=tuple(profiles),
    )


def affected_profiles(
    paths: list[str], catalog: Catalog, root: Path
) -> tuple[str, ...]:
    """Return the profiles whose closure contains what ``paths`` changed."""
    return affected_scope(paths, catalog, root).profiles


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
        prog="rpent-install affected",
        description="Map changed paths to affected components, tests and profiles.",
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
        help="restrict the profiles to the ones one runner installs",
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
            profiles=tuple(name for name in scope.profiles if name in allowed),
            pr_profiles=tuple(name for name in scope.pr_profiles if name in allowed),
        )
    print(json.dumps(scope.as_dict()))
    return 0


if __name__ == "__main__":
    print(
        "run `rpent-install affected` instead of this module",
        file=sys.stderr,
    )
    raise SystemExit(2)
