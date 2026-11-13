#!/usr/bin/env python3
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

"""Check component ownership and import boundaries from a_1 section 4.6.

Rules:

- ``toolkits/*`` must not import ``robots`` or ``robots.<name>``.
- ``robots/<a>`` must not import another ``robots.<b>`` unless the two
  integrations declare each other through ``requires`` (a co-installed
  extension such as dual Franka reusing the Franka pipeline).
- capabilities under ``rpent/robots/components/<name>/`` must not import robots.
- core ``rpent/**`` must not import ``toolkits.*`` or a concrete ``robots.<x>``.
  Importing the ``robots`` package itself for discovery is allowed.

The script also checks that every ``robots/*``, ``toolkits/*`` and capability
directory declares a ``component.toml`` with the matching kind.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpent.install.discovery import discover_components  # noqa: E402
from rpent.install.errors import InstallConfigError  # noqa: E402


@dataclass(frozen=True)
class Finding:
    """One layout violation."""

    path: Path
    line: int
    message: str


def _imports(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append((node.lineno, node.module))
    return imports


def _concrete_robot(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "robots":
        return parts[1]
    return None


def _owner(path: Path, root: Path) -> tuple[str, str] | None:
    relative = path.relative_to(root).parts
    if not relative:
        return None
    if relative[0] == "robots" and len(relative) > 1:
        return "robot", relative[1]
    if relative[0] == "toolkits" and len(relative) > 1:
        return "toolkit", relative[1]
    if (
        len(relative) > 4
        and relative[0] == "rpent"
        and relative[1] == "robots"
        and relative[2] == "components"
    ):
        return "capability", relative[3]
    if relative[0] == "rpent":
        return "core", ""
    return None


def _declared_robot_imports(root: Path) -> dict[str, set[str]]:
    """Return robot -> robots it may import because they install together."""
    try:
        components = discover_components(root)
    except InstallConfigError:
        return {}
    declared = {
        name: set(component.requires)
        for name, component in components.items()
        if component.kind == "robot"
    }
    for name, requires in list(declared.items()):
        for other in requires:
            declared.setdefault(other, set()).add(name)
    return declared


def check_imports(root: Path) -> list[Finding]:
    """Return import boundary violations under ``root``."""
    findings: list[Finding] = []
    declared_imports = _declared_robot_imports(root)
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("."):
            # AppleDouble metadata for a synced checkout, not source.
            continue
        if any(part in {".git", ".rpent", "tests", "docs"} for part in path.parts):
            continue
        owner = _owner(path, root)
        if owner is None:
            continue
        kind, name = owner
        for line, module in _imports(path):
            robot = _concrete_robot(module)
            if kind == "toolkit":
                if module == "robots" or robot is not None:
                    findings.append(
                        Finding(path, line, "toolkits must not import robots")
                    )
            elif kind == "robot":
                if (
                    robot is not None
                    and robot != name
                    and robot not in declared_imports.get(name, set())
                ):
                    findings.append(
                        Finding(
                            path,
                            line,
                            f"robot {name!r} must not import robot {robot!r}; "
                            "declare a co-installed extension in component.toml "
                            "requires if that is intentional",
                        )
                    )
            elif kind == "capability":
                if robot is not None:
                    findings.append(
                        Finding(
                            path,
                            line,
                            f"capability {name!r} must not import robots",
                        )
                    )
            elif kind == "core":
                if module == "toolkits" or module.startswith("toolkits."):
                    findings.append(
                        Finding(path, line, "core must not import toolkits")
                    )
                if robot is not None:
                    findings.append(
                        Finding(
                            path,
                            line,
                            f"core must not import concrete robot {robot!r}",
                        )
                    )
    return findings


def check_coverage(root: Path) -> list[Finding]:
    """Return missing or mismatched component manifests."""
    findings: list[Finding] = []
    try:
        components = discover_components(root)
    except InstallConfigError as exc:
        return [Finding(root / "component.toml", 0, str(exc))]
    declared = {component.path.resolve() for component in components.values()}
    roots = [
        (root / "robots", "robot"),
        (root / "toolkits", "toolkit"),
        (root / "rpent" / "robots" / "components", "capability"),
    ]
    for directory, kind in roots:
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            if kind == "capability" and not any(child.glob("*.py")):
                continue
            if child.resolve() not in declared:
                findings.append(
                    Finding(
                        child / "component.toml",
                        0,
                        f"{kind} directory has no component.toml",
                    )
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(prog="check_layout.py")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to check.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    findings = check_coverage(root) + check_imports(root)
    for finding in findings:
        location = (
            finding.path.relative_to(root)
            if finding.path.is_relative_to(root)
            else finding.path
        )
        suffix = f":{finding.line}" if finding.line else ""
        print(f"{location}{suffix}: {finding.message}")
    if findings:
        print(f"{len(findings)} layout violation(s)", file=sys.stderr)
        return 1
    print("layout ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
