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

Loading the catalog already rejects an invalid manifest, a duplicate component
or target name, a broken ``requires``/``imports``/``env_conflicts`` reference,
and a deps component with a single consumer. This tool adds the checks that
need a target: its closure, placement, and variant selection resolve, and every
robot component is selected by an explicit target.

Checked-in locks are optional reproduction artifacts, not installation inputs,
so this tool neither requires nor validates them. ``--resolve`` compiles the
declared dependencies with uv to prove they have a solution; ``--inputs-hash``
prints the cache-key inputs an install would record.

Usage::

    python -m tests.tooling.check --all
    python -m tests.tooling.check robotwin --resolve
    python -m tests.tooling.check robotwin --inputs-hash
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.installer import find_uv
from rpent.install.lock import resolve_target
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
    uv: str | None = None,
) -> list[str]:
    """Return every problem with one target, or an empty list."""
    target = catalog.targets[name]
    core = read_core_dependencies(root) if target.core else ()
    resolution = resolve(target, catalog, core_dependencies=core)
    problems = [*resolution.errors]
    if problems or uv is None:
        return problems
    try:
        lock_text = resolve_target(target, catalog, root=root, uv=uv)
    except InstallError as exc:
        return [str(exc)]
    pinned = sum(
        1 for line in lock_text.splitlines() if line and not line.startswith((" ", "#"))
    )
    print(f"target {name}: uv resolved {pinned} requirements")
    return []


def inputs_hash(name: str, catalog: Catalog, root: Path) -> tuple[str, str]:
    """Return the installed-inputs hash and Python minor for one target.

    The hash covers the target, its component manifests, overrides, core
    dependencies, and the checkout's ``[tool.uv]`` settings, so CI can key a
    prebuilt environment on the manifests instead of a lock.
    """
    target = catalog.targets[name]
    core = read_core_dependencies(root) if target.core else ()
    resolution = resolve(target, catalog, core_dependencies=core)
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    if resolution.python is None:
        raise InstallError(f"target {name!r} resolved no Python minor")
    digest = requirements_sha256(resolution, root=root, core_dependencies=core)
    return digest, resolution.python


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the named targets, or every target with ``--all``."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.tooling.check",
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
        "--inputs-hash",
        action="store_true",
        help="print the installed-inputs hash and Python minor for one target",
    )
    args = parser.parse_args(argv)
    catalog = discover(root)
    names = sorted(catalog.targets) if args.all else args.targets
    if not names:
        parser.error("pass a target name or --all")
    if args.inputs_hash:
        if len(names) != 1 or args.all:
            parser.error("--inputs-hash takes exactly one target")
        name = names[0]
        if name not in catalog.targets:
            known = ", ".join(sorted(catalog.targets))
            print(f"unknown target {name!r}; known targets: {known}", file=sys.stderr)
            return 1
        try:
            digest, python = inputs_hash(name, catalog, root)
        except InstallError as exc:
            print(f"target {name}: FAIL\n  {exc}", file=sys.stderr)
            return 1
        print(f"inputs={digest}")
        print(f"python={python}")
        return 0
    uv = find_uv() if args.resolve else None
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
        problems = check_target(name, catalog, root, uv=uv)
        if problems:
            failed = True
            print(f"target {name}: FAIL")
            for problem in problems:
                print(f"  {problem}")
            continue
        core = read_core_dependencies(root) if catalog.targets[name].core else ()
        resolution = resolve(catalog.targets[name], catalog, core_dependencies=core)
        print(f"target {name}: ok")
        installed = ", ".join(sorted(resolution.main_installed())) or "(core only)"
        print(f"  installs: {installed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(root=Path.cwd()))
