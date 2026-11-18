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

"""``rpent-install``: list, install, and diagnose profile environments.

Supported targets are the named profiles in ``installs/profiles/`` and
``tests/profiles/``. Repository checks and lock generation are maintainer
tools under ``tests/tooling/`` and are not part of this command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import discover
from rpent.install.doctor import FAIL, check_installation
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import current_venv
from rpent.install.installer import install
from rpent.utils.config import get_repo_root


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
        print(f"  {name:<28} python {profile.python:<4} {components}")
    return 0


def command_install(args: argparse.Namespace) -> int:
    """Create or reuse a virtualenv and install one profile."""
    install(
        args.profile,
        root=args.root,
        venv=args.venv,
        force=args.force,
        verbose=True,
    )
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``rpent-install``."""
    parser = argparse.ArgumentParser(
        prog="rpent-install",
        description="Install and diagnose RPent profile environments.",
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

    installer = subcommands.add_parser(
        "install", help="install one named profile into a virtualenv"
    )
    installer.add_argument("profile")
    installer.add_argument("--venv", type=Path, help="virtualenv path")
    installer.add_argument(
        "--force",
        action="store_true",
        help="install into a non-empty virtualenv that records no fingerprint",
    )
    installer.set_defaults(handler=command_install)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``rpent-install`` and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (InstallError, InstallConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
