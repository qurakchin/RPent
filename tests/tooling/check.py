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

"""Validate every manifest, profile closure, and lock without installing.

Loading the catalog already rejects an invalid manifest, a duplicate component
or profile name, a broken ``requires``/``imports``/``env_conflicts`` reference,
and a deps component with a single consumer. This tool adds the checks that
need a profile: its closure, placement, and variant selection resolve, and the
declared lock still covers the resulting requirements.

Usage::

    python -m tests.tooling.check --all
    python -m tests.tooling.check sim-robotwin --resolve
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.installer import find_uv
from rpent.install.lock import resolve_profile
from rpent.install.lock_coverage import lock_problems
from rpent.install.requirements import read_core_dependencies
from rpent.install.resolve import resolve

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_profile(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    uv: str | None = None,
) -> list[str]:
    """Return every problem with one profile, or an empty list."""
    profile = catalog.profiles[name]
    core = read_core_dependencies(root) if profile.core else ()
    resolution = resolve(profile, catalog, core_dependencies=core)
    problems = [*resolution.errors]
    problems.extend(lock_problems(profile, resolution, root, core_dependencies=core))
    if problems or uv is None:
        return problems
    try:
        lock_text = resolve_profile(profile, catalog, root=root, uv=uv)
    except InstallError as exc:
        return [str(exc)]
    pinned = sum(
        1 for line in lock_text.splitlines() if line and not line.startswith((" ", "#"))
    )
    print(f"profile {name}: uv resolved {pinned} requirements")
    return []


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the named profiles, or every profile with ``--all``."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.tooling.check",
        description="Validate profiles and their locks without installing.",
    )
    parser.add_argument("profiles", nargs="*", help="profile names to check")
    parser.add_argument("--all", action="store_true", help="check every profile")
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="also compile each profile with uv to prove it resolves",
    )
    args = parser.parse_args(argv)
    catalog = discover(root)
    names = sorted(catalog.profiles) if args.all else args.profiles
    if not names:
        parser.error("pass a profile name or --all")
    uv = find_uv() if args.resolve else None
    failed = False
    for name in names:
        if name not in catalog.profiles:
            known = ", ".join(sorted(catalog.profiles))
            print(f"unknown profile {name!r}; known profiles: {known}", file=sys.stderr)
            failed = True
            continue
        problems = check_profile(name, catalog, root, uv=uv)
        if problems:
            failed = True
            print(f"profile {name}: FAIL")
            for problem in problems:
                print(f"  {problem}")
            continue
        core = read_core_dependencies(root) if catalog.profiles[name].core else ()
        resolution = resolve(catalog.profiles[name], catalog, core_dependencies=core)
        print(f"profile {name}: ok")
        installed = ", ".join(sorted(resolution.main_installed())) or "(core only)"
        print(f"  installs: {installed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(root=Path.cwd()))
