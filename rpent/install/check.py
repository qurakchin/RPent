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

"""Validate every manifest and target closure without installing.

``rpent-install check`` resolves targets from their manifests and reports what
the installer would reject. Loading the catalog already rejects an invalid
manifest, a duplicate component or target name, and a broken
``requires``/``imports``/``env_conflicts`` reference. This module adds the
checks that need a target: its closure resolves for a host, and every robot
component is selected by an explicit target.

Checked-in locks are optional reproduction artifacts, not installation inputs,
so this command neither requires nor validates them. ``--resolve`` compiles the
declared dependencies with uv to prove they have a solution; ``--inputs-hash``
prints the cache-key inputs an install would record.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.installer import find_uv
from rpent.install.lock import resolve_target
from rpent.install.manifest import DEFAULT_PLATFORMS
from rpent.install.requirements import (
    read_core_dependencies,
    requirements_sha256,
)
from rpent.install.resolve import resolve

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_catalog(catalog: Catalog) -> list[str]:
    """Return problems with the target set as a whole.

    Robot components do not form same-name targets, so a robot that no target
    selects cannot be installed at all. Installing a robot means choosing the
    composition it runs in, which only a target file can declare.
    """
    problems: list[str] = []
    for name, component in sorted(catalog.components.items()):
        if component.kind != "robot":
            continue
        providers = sorted(
            target.name
            for target in catalog.targets.values()
            if name in target.components
        )
        if not providers:
            problems.append(
                f"robot component {component.manifest_path} is not selected by "
                f"any target; add installs/targets/<target>.toml with "
                f"[components.{name}]"
            )
    return problems


def check_target(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    platform: str = DEFAULT_PLATFORMS[0],
    uv: str | None = None,
) -> list[str]:
    """Return every problem with one target, or an empty list."""
    target = catalog.targets[name]
    core = read_core_dependencies(root) if target.core else ()
    resolution = resolve(
        target, catalog, core_dependencies=core, platform=platform
    )
    problems = [*resolution.errors]
    if problems or uv is None:
        return problems
    try:
        lock_text = resolve_target(
            target, catalog, root=root, uv=uv, platform=platform
        )
    except InstallError as exc:
        return [str(exc)]
    pinned = sum(
        1
        for line in lock_text.splitlines()
        if line and not line.startswith((" ", "#", "-"))
    )
    print(f"target {name}: uv resolved {pinned} requirements for {platform}")
    return []


def inputs_hash(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    platform: str = DEFAULT_PLATFORMS[0],
) -> tuple[str, str]:
    """Return the installed-inputs hash and Python minor for one target.

    The hash covers the target, its component manifests, overrides, core
    dependencies, the host, and the checkout's ``[tool.uv]`` settings, so CI can
    key a prebuilt environment on the manifests instead of a lock.
    """
    target = catalog.targets[name]
    core = read_core_dependencies(root) if target.core else ()
    resolution = resolve(
        target, catalog, core_dependencies=core, platform=platform
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    if resolution.python is None:
        raise InstallError(f"target {name!r} resolved no Python minor")
    digest = requirements_sha256(resolution, root=root, core_dependencies=core)
    return digest, resolution.python


def run_check(
    *,
    targets: list[str],
    all_targets: bool,
    resolve_deps: bool,
    platform: str,
    inputs_hash_only: bool,
    root: Path,
) -> int:
    """Print the check report and return a process exit code."""
    catalog = discover(root)
    names = sorted(catalog.targets) if all_targets else targets
    if not names:
        print("pass a target name or --all", file=sys.stderr)
        return 2
    if inputs_hash_only:
        if len(names) != 1 or all_targets:
            print("--inputs-hash takes exactly one target", file=sys.stderr)
            return 2
        name = names[0]
        if name not in catalog.targets:
            known = ", ".join(sorted(catalog.targets))
            print(f"unknown target {name!r}; known targets: {known}", file=sys.stderr)
            return 1
        try:
            digest, python = inputs_hash(name, catalog, root, platform=platform)
        except InstallError as exc:
            print(f"target {name}: FAIL\n  {exc}", file=sys.stderr)
            return 1
        print(f"inputs={digest}")
        print(f"python={python}")
        return 0
    uv = find_uv() if resolve_deps else None
    failed = False
    catalog_problems = check_catalog(catalog)
    if catalog_problems:
        failed = True
        print("catalog: FAIL")
        for problem in catalog_problems:
            print(f"  {problem}")
    for name in names:
        if name not in catalog.targets:
            known = ", ".join(sorted(catalog.targets))
            print(f"unknown target {name!r}; known targets: {known}", file=sys.stderr)
            failed = True
            continue
        problems = check_target(
            name, catalog, root, platform=platform, uv=uv
        )
        if problems:
            failed = True
            print(f"target {name}: FAIL")
            for problem in problems:
                print(f"  {problem}")
            continue
        target = catalog.targets[name]
        core = read_core_dependencies(root) if target.core else ()
        resolution = resolve(
            target, catalog, core_dependencies=core, platform=platform
        )
        print(f"target {name}: ok (python {resolution.python})")
        installed = ", ".join(sorted(resolution.components)) or "(core only)"
        print(f"  installs: {installed}")
    return 1 if failed else 0


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the named targets, or every target with ``--all``."""
    parser = argparse.ArgumentParser(
        prog="rpent-install check",
        description="Validate targets without installing.",
    )
    parser.add_argument("targets", nargs="*", help="target names to check")
    parser.add_argument("--all", action="store_true", help="check every target")
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="also compile each target with uv to prove it resolves",
    )
    parser.add_argument(
        "--platform",
        default=DEFAULT_PLATFORMS[0],
        help="host to resolve for, such as linux-x86_64 or darwin-arm64",
    )
    parser.add_argument(
        "--inputs-hash",
        action="store_true",
        help="print the installed-inputs hash and Python minor for one target",
    )
    args = parser.parse_args(argv)
    return run_check(
        targets=list(args.targets),
        all_targets=args.all,
        resolve_deps=args.resolve,
        platform=args.platform,
        inputs_hash_only=args.inputs_hash,
        root=root,
    )


if __name__ == "__main__":
    raise SystemExit(main(root=Path.cwd()))
