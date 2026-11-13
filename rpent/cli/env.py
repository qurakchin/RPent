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

"""``rpent-env``: inspect, check, install, lock, and diagnose environments.

Supported targets are the named profiles in ``envs/``. Component names are
accepted by ``install`` as a development diagnostic only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.doctor import FAIL, check_installation, inspect_installation
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import current_venv
from rpent.install.installer import install, resolve_install_target
from rpent.install.lock import lock_profiles
from rpent.install.locks import lock_problems
from rpent.install.requirements import read_core_dependencies
from rpent.install.resolve import Resolution, resolve
from rpent.utils.config import get_repo_root


def _resolution(target: str, catalog: Catalog, root: Path) -> Resolution:
    return resolve_install_target(target, catalog, root=root)


def _describe_environment(resolution: Resolution, environment: str) -> str:
    names = resolution.environments().get(environment, ())
    return f"{environment}: {', '.join(names) or '(core only)'}"


def command_list(args: argparse.Namespace) -> int:
    """Print components and profiles."""
    catalog = discover(args.root)
    print("Components")
    for name, component in sorted(catalog.components.items()):
        placements = ", ".join(component.placements)
        print(f"  {name:<20} {component.kind:<10} {placements}")
    print("\nProfiles")
    for name, profile in sorted(catalog.profiles.items()):
        components = ", ".join(sorted(profile.components)) or "(core only)"
        print(f"  {name:<20} python {profile.python:<4} {components}")
    return 0


def command_check(args: argparse.Namespace) -> int:
    """Resolve profiles without installing anything."""
    catalog = discover(args.root)
    names = sorted(catalog.profiles) if args.all else args.profiles
    if not names:
        print("pass a profile name or --all", file=sys.stderr)
        return 2
    failed = False
    for name in names:
        try:
            profile = catalog.profiles[name]
        except KeyError:
            known = ", ".join(sorted(catalog.profiles))
            print(f"unknown profile {name!r}; known profiles: {known}", file=sys.stderr)
            failed = True
            continue
        core = read_core_dependencies(args.root) if profile.core else ()
        resolution = resolve(profile, catalog, core_dependencies=core)
        problems = lock_problems(profile, resolution, args.root, core_dependencies=core)
        if not resolution.ok or problems:
            failed = True
            print(f"profile {name}: FAIL")
            for error in [*resolution.errors, *problems]:
                print(f"  {error}")
            continue
        print(f"profile {name}: ok")
        for environment in sorted(resolution.nonempty_environments()):
            print(f"  {_describe_environment(resolution, environment)}")
    return 1 if failed else 0


def command_install(args: argparse.Namespace) -> int:
    """Create or reuse a virtualenv and install one target."""
    install(
        args.target,
        root=args.root,
        venv=args.venv,
        include_dev=args.dev,
        dry_run=args.dry_run,
        verbose=True,
    )
    return 0


def command_lock(args: argparse.Namespace) -> int:
    """Compile or verify profile locks."""
    if args.all:
        targets: list[str] = []
    else:
        targets = args.profiles
        if not targets:
            print("pass a profile name or --all", file=sys.stderr)
            return 2
    return lock_profiles(targets, root=args.root, check=args.check)


def _parse_endpoints(values: list[str]) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    for value in values:
        name, separator, endpoint = value.partition("=")
        if not separator or not name or not endpoint:
            raise InstallError(f"invalid --endpoint {value!r}; expected NAME=host:port")
        endpoints[name] = endpoint
    return endpoints


def command_doctor(args: argparse.Namespace) -> int:
    """Check the current or selected virtualenv."""
    venv = args.venv or current_venv()
    if venv is None:
        print(
            "no active virtualenv; activate one or pass --venv",
            file=sys.stderr,
        )
        return 2
    checks = check_installation(
        venv,
        profile_name=args.profile,
        endpoints=_parse_endpoints(args.endpoint),
        root=args.root,
    )
    for check in checks:
        print(f"{check.status:<4} {check.message}")
    return 1 if any(check.status == FAIL for check in checks) else 0


def command_inspect(args: argparse.Namespace) -> int:
    """Print the stored installation fingerprint."""
    venv = args.venv or current_venv()
    if venv is None:
        print("no active virtualenv; activate one or pass --venv", file=sys.stderr)
        return 2
    report = inspect_installation(venv)
    if report is None:
        print(f"{venv} has no installation fingerprint", file=sys.stderr)
        return 1
    print(f"venv: {report['venv']}")
    print(f"sha256: {report['sha256']}")
    for key in sorted(report["fingerprint"]):
        value = report["fingerprint"][key]
        if isinstance(value, dict):
            print(f"{key}:")
            for nested, nested_value in sorted(value.items()):
                print(f"  {nested}: {nested_value}")
        else:
            print(f"{key}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``rpent-env``."""
    parser = argparse.ArgumentParser(
        prog="rpent-env",
        description="Install and diagnose RPent component environments.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=get_repo_root(),
        help="RPent checkout to read manifests from.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list", help="list components and profiles")
    listing.set_defaults(handler=command_list)

    check = subcommands.add_parser("check", help="validate profiles without installing")
    check.add_argument("profiles", nargs="*")
    check.add_argument("--all", action="store_true", help="check every profile")
    check.set_defaults(handler=command_check)

    installer = subcommands.add_parser(
        "install", help="install a profile (or one component for diagnostics)"
    )
    installer.add_argument("target")
    installer.add_argument("--venv", type=Path, help="virtualenv path")
    installer.add_argument(
        "--dev", action="store_true", help="also install the dev profile"
    )
    installer.add_argument(
        "--dry-run", action="store_true", help="print requirements only"
    )
    installer.set_defaults(handler=command_install)

    lock = subcommands.add_parser("lock", help="compile or verify dependency locks")
    lock.add_argument("profiles", nargs="*")
    lock.add_argument("--all", action="store_true", help="lock every profile")
    lock.add_argument(
        "--check", action="store_true", help="fail when a lock is out of date"
    )
    lock.set_defaults(handler=command_lock)

    doctor = subcommands.add_parser("doctor", help="diagnose an installed venv")
    doctor.add_argument("--venv", type=Path)
    doctor.add_argument("--profile", help="profile name; defaults to fingerprint")
    doctor.add_argument(
        "--endpoint",
        action="append",
        default=[],
        metavar="NAME=HOST:PORT",
        help="external environment endpoint; may be repeated",
    )
    doctor.set_defaults(handler=command_doctor)

    inspect = subcommands.add_parser(
        "inspect", help="print the installation fingerprint"
    )
    inspect.add_argument("--venv", type=Path)
    inspect.set_defaults(handler=command_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``rpent-env`` and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (InstallError, InstallConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
