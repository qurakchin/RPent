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

"""``rpent-install``: list, install, and diagnose target environments.

A target is a non-robot component installed under its own name, or a file in
``installs/targets/`` or ``tests/targets/`` that composes components or selects
a robot. Repository checks and lock generation are maintainer tools under
``tests/tooling/`` and are not part of this command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpent.install.discovery import discover
from rpent.install.doctor import FAIL, check_installation
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import (
    SUPPORTED_PLATFORM,
    activated_venv,
    current_venv,
    runtime_platform,
)
from rpent.install.installer import install
from rpent.utils.config import get_repo_root


def _require_supported_platform() -> None:
    """Reject hosts RPent does not install wheels for."""
    current = runtime_platform()
    if current != SUPPORTED_PLATFORM:
        raise InstallError(
            f"RPent installs only on {SUPPORTED_PLATFORM}; this host is {current}"
        )


def command_list(args: argparse.Namespace) -> int:
    """Print components and targets."""
    catalog = discover(args.root)
    print("Components")
    for name, component in sorted(catalog.components.items()):
        description = component.settings.description or ""
        print(f"  {name:<20} {component.kind:<10} {description}".rstrip())
    print("\nTargets")
    for name, target in sorted(catalog.targets.items()):
        components = ", ".join(sorted(target.components)) or "(core only)"
        print(f"  {name:<28} python {target.python:<12} {components}")
    return 0


def command_install(args: argparse.Namespace) -> int:
    """Create or reuse a virtualenv and install one target."""
    _require_supported_platform()
    install(
        args.target,
        root=args.root,
        venv=args.venv,
        force=args.force,
        verbose=True,
        dry_run=args.dry_run,
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
    _require_supported_platform()
    # Prefer the environment the user activated: `rpent-install` may be running
    # from a tool environment while the target environment is activated.
    venv = args.venv or activated_venv() or current_venv()
    if venv is None:
        print(
            "no active virtualenv; activate one or pass --venv <path>",
            file=sys.stderr,
        )
        return 2
    checks = check_installation(
        venv,
        target_name=args.target,
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
        description="Install and diagnose RPent target environments.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=get_repo_root(),
        help="RPent checkout to read manifests from.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list", help="list components and targets")
    listing.set_defaults(handler=command_list)

    installer = subcommands.add_parser(
        "install", help="install one named target into a virtualenv"
    )
    installer.add_argument("target")
    installer.add_argument("--venv", type=Path, help="virtualenv path")
    installer.add_argument(
        "--force",
        action="store_true",
        help="install into a non-empty virtualenv that records no fingerprint",
    )
    installer.add_argument(
        "--dry-run",
        action="store_true",
        help="print the requirements the target resolves to without installing",
    )
    installer.set_defaults(handler=command_install)

    doctor = subcommands.add_parser("doctor", help="diagnose an installed venv")
    doctor.add_argument("--venv", type=Path)
    doctor.add_argument("--target", help="target name; defaults to fingerprint")
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
