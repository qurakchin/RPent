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

"""Validate component environments without installing.

``rpent-install check`` resolves the environment a component forms and reports
what the installer would reject. Loading the catalog already rejects an invalid
manifest and a broken ``requires``/``imports``/``env_conflicts`` reference. This
module adds the checks that need resolution: the closure resolves for a host.

Checked-in locks are optional reproduction artifacts, not installation inputs,
so this command neither requires nor validates them. ``--resolve`` compiles the
declared dependencies with uv to prove they have a solution; ``--inputs-hash``
prints the cache-key inputs an install would record.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import (
    Catalog,
    discover,
    environment_names,
    requested_components,
)
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.installer import find_uv
from rpent.install.lock import resolve_environment
from rpent.install.manifest import DEFAULT_PLATFORMS, MINIMAL_ENVIRONMENT
from rpent.install.requirements import (
    read_core_dependencies,
    requirements_sha256,
)
from rpent.install.resolve import Resolution, resolve

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_catalog(catalog: Catalog) -> list[str]:
    """Return problems with the names the environment namespace reserves.

    An environment name joins its requested components with ``+``, so a
    component must not contain the separator or the name cannot be split back
    into what was requested.
    """
    problems: list[str] = []
    for name, component in sorted(catalog.components.items()):
        if "+" in name:
            problems.append(
                f"component {component.manifest_path} is named {name!r}; a "
                "component name must not contain '+'"
            )
    return problems


def _resolution(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    platform: str,
) -> Resolution:
    return resolve(
        requested_components(name, catalog.components),
        catalog,
        core_dependencies=read_core_dependencies(root),
        platform=platform,
    )


def check_environment(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    platform: str = DEFAULT_PLATFORMS[0],
    uv: str | None = None,
) -> list[str]:
    """Return every problem with one environment, or an empty list."""
    try:
        requested = requested_components(name, catalog.components)
        resolution = _resolution(name, catalog, root, platform=platform)
    except (InstallConfigError, InstallError) as exc:
        return [str(exc)]
    problems = [*resolution.errors]
    if problems or uv is None:
        return problems
    try:
        lock_text = resolve_environment(
            requested, catalog, root=root, uv=uv, platform=platform
        )
    except InstallError as exc:
        return [str(exc)]
    pinned = sum(
        1
        for line in lock_text.splitlines()
        if line and not line.startswith((" ", "#", "-"))
    )
    print(f"{name}: uv resolved {pinned} requirements for {platform}")
    return []


def inputs_hash(
    name: str,
    catalog: Catalog,
    root: Path,
    *,
    platform: str = DEFAULT_PLATFORMS[0],
) -> tuple[str, str]:
    """Return the installed-inputs hash and Python minor for one environment.

    The hash covers the component closure, overrides, core dependencies, the
    host, and the checkout's ``[tool.uv]`` settings, so CI can key a prebuilt
    environment on the manifests instead of a lock.
    """
    resolution = _resolution(name, catalog, root, platform=platform)
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    if resolution.python is None:
        raise InstallError(f"environment {name!r} resolved no Python minor")
    digest = requirements_sha256(
        resolution,
        root=root,
        core_dependencies=read_core_dependencies(root),
    )
    return digest, resolution.python


def run_check(
    *,
    components: list[str],
    all_environments: bool,
    resolve_deps: bool,
    platform: str,
    inputs_hash_only: bool,
    root: Path,
) -> int:
    """Print the check report and return a process exit code."""
    catalog = discover(root)
    if all_environments:
        selected = list(environment_names(catalog.components))
    elif components:
        selected = components
    else:
        selected = [MINIMAL_ENVIRONMENT]
    if inputs_hash_only:
        if len(selected) != 1 or all_environments:
            print("--inputs-hash takes exactly one environment", file=sys.stderr)
            return 2
        name = selected[0]
        try:
            digest, python = inputs_hash(name, catalog, root, platform=platform)
        except (InstallConfigError, InstallError) as exc:
            print(f"{name}: FAIL\n  {exc}", file=sys.stderr)
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
    for name in selected:
        problems = check_environment(name, catalog, root, platform=platform, uv=uv)
        if problems:
            failed = True
            print(f"{name}: FAIL")
            for problem in problems:
                print(f"  {problem}")
            continue
        resolution = _resolution(name, catalog, root, platform=platform)
        print(f"{name}: ok (python {resolution.python})")
        installed = ", ".join(sorted(resolution.components)) or "(core only)"
        print(f"  installs: {installed}")
    return 1 if failed else 0


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the named environments, or every component with ``--all``."""
    parser = argparse.ArgumentParser(
        prog="rpent-install check",
        description="Validate component environments without installing.",
    )
    parser.add_argument(
        "components",
        nargs="*",
        help="component names or the minimal environment; empty checks minimal",
    )
    parser.add_argument(
        "--all", action="store_true", help="check every component and minimal"
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="also compile each environment with uv to prove it resolves",
    )
    parser.add_argument(
        "--platform",
        default=DEFAULT_PLATFORMS[0],
        help="host to resolve for, such as linux-x86_64 or darwin-arm64",
    )
    parser.add_argument(
        "--inputs-hash",
        action="store_true",
        help="print the installed-inputs hash and Python minor for one environment",
    )
    parser.set_defaults(handler=_run_args)
    args = parser.parse_args(argv)
    return args.handler(args, root=root)


def _run_args(args: argparse.Namespace, *, root: Path) -> int:
    return run_check(
        components=args.components,
        all_environments=args.all,
        resolve_deps=args.resolve,
        platform=args.platform,
        inputs_hash_only=args.inputs_hash,
        root=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
