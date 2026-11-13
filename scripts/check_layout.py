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

"""Check repository layout and import boundaries from a_1 section 4.6.

Rules:

- K1: top-level directories and root files match the a_1 4.1 whitelist.
- K2: every component directory declares a ``component.toml`` with the
  matching kind (manifest validity is left to ``rpent-env check``) and has the
  role files its kind requires (a_1 4.2, a_3 4.3 and 4.7).
- K3: a slice root must not add a name a_1 4.2 retires, and a migrated slice
  must not keep one. Components that predate the skeleton only warn until
  a_5 moves them.
- K4: ``toolkits/`` and ``capabilities/`` must not import ``robots``, and
  slices, toolkits, or capabilities must not import a sibling of their own
  kind unless the manifest declares it in ``imports``. Core ``rpent/**`` must
  not import ``toolkits``, ``capabilities``, or a concrete ``robots.<name>``;
  importing the ``robots`` package itself for discovery is allowed.
- K5: core ``rpent/**`` must not name a robot or benchmark (R8).
- K6: a slice ``robots/<name>/__init__.py`` only re-exports lazily.
- K7: ``spec.py`` > 80, ``adapter.py`` > 400, and ``native_tools.py`` > 100
  lines are reported as warnings until a_5 splits them.

``rpent/robots/components/__init__.py`` is the documented compatibility shim
that forwards to ``capabilities._base`` for one release, so K4 exempts it.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tokenize
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpent.install.discovery import discover_components  # noqa: E402
from rpent.install.errors import InstallConfigError  # noqa: E402

#: Directories a_1 4.1 registers an owner for. Hidden directories are tool
#: configuration and are exempt.
ALLOWED_TOP_LEVEL = frozenset(
    {"rpent", "robots", "toolkits", "capabilities", "envs", "tests", "docs", "scripts"}
)
#: Root files a_1 4.1 allows next to the top-level directories.
ALLOWED_ROOT_FILES = (
    "pyproject.toml",
    "README*",
    "CONTRIBUTING*",
    "LICENSE",
    "AGENTS.md",
    "CLAUDE.md",
    ".gitignore",
    ".pre-commit-config.yaml",
)
#: Generated, gitignored directories that may appear in a working checkout.
IGNORED_TOP_LEVEL = frozenset({"memory", "__pycache__"})
#: The compatibility shim allowed to forward into ``capabilities``.
CORE_EXEMPTIONS = frozenset({"rpent/robots/components/__init__.py"})
#: Line-count limits from K7; exceeded counts are warnings until a_5 splits.
LINE_LIMITS = {"spec.py": 80, "adapter.py": 400, "native_tools.py": 100}
#: Names a_1 4.2 retires from a slice root once its migration lands.
LEGACY_SLICE_NAMES = frozenset(
    {
        "robot_spec.py",
        "prompt_bundle.py",
        "env_client.py",
        "env_server.py",
        "toolkit.py",
        "tools.py",
        "primitives.py",
        "rlinf_env.py",
        "rpent_env.py",
        "runtime_config.py",
        "tasks.py",
        "suites.py",
        "eval",
    }
)
#: Slices that still carry legacy names, recorded from the baseline. Entries
#: disappear as a_5 completes; anything added here again is a regression.
LEGACY_SLICES = {
    "dual_franka": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "prompt_bundle.py",
            "robot_spec.py",
            "rpent_env.py",
            "runtime_config.py",
            "tasks.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "franka": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "prompt_bundle.py",
            "robot_spec.py",
            "rpent_env.py",
            "runtime_config.py",
            "tasks.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "libero": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "prompt_bundle.py",
            "robot_spec.py",
            "suites.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "robocasa": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "eval",
            "primitives.py",
            "prompt_bundle.py",
            "robot_spec.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "robodojo": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "primitives.py",
            "prompt_bundle.py",
            "rlinf_env.py",
            "robot_spec.py",
            "tasks.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "robotwin": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "eval",
            "primitives.py",
            "prompt_bundle.py",
            "rlinf_env.py",
            "robot_spec.py",
            "toolkit.py",
            "tools.py",
        }
    ),
    "yam": frozenset(
        {
            "env_client.py",
            "env_server.py",
            "primitives.py",
            "prompt_bundle.py",
            "rlinf_env.py",
            "robot_spec.py",
            "runtime_config.py",
            "tasks.py",
            "toolkit.py",
            "tools.py",
        }
    ),
}
#: Slices whose a_5 migration is complete; K3 becomes an error for them.
MIGRATED_SLICES: frozenset[str] = frozenset()
#: Required role files per kind (a_1 4.2, a_3 4.3, a_3 4.7).
REQUIRED_ROLE_FILES = {
    "robot": (
        "__init__.py",
        "spec.py",
        "config.py",
        "adapter.py",
        "prompts/__init__.py",
        "prompts/domain.py",
        "prompts/tools.py",
    ),
    "toolkit": ("__init__.py", "tool.py", "core.py", "observation.py", "evaluation"),
    "capability": ("__init__.py", "server.py", "config.py", "README.md"),
}
#: Components that predate the target skeleton; missing role files warn until
#: a_5 (robots) and a_3 (toolkits, capabilities) land.
LEGACY_COMPONENTS = frozenset(
    {
        ("robot", "dual_franka"),
        ("robot", "franka"),
        ("robot", "libero"),
        ("robot", "robocasa"),
        ("robot", "robodojo"),
        ("robot", "robotwin"),
        ("robot", "yam"),
        ("toolkit", "geometry"),
        ("capability", "apxinf"),
        ("capability", "cosmos3"),
        ("capability", "cosmos_policy"),
        ("capability", "fast_wam"),
        ("capability", "molmo"),
        ("capability", "openpi"),
        ("capability", "sam3"),
        ("capability", "xpolicylab"),
    }
)
ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """One layout violation."""

    path: Path
    line: int
    message: str
    level: str = ERROR


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
        elif isinstance(node, ast.Call):
            target = _literal_import_target(node)
            if target is not None:
                imports.append((node.lineno, target))
    return imports


def _literal_import_target(node: ast.Call) -> str | None:
    """Return the module named by ``import_module("...")`` and friends."""
    function = node.func
    if isinstance(function, ast.Name):
        name = function.id
    elif isinstance(function, ast.Attribute):
        name = function.attr
    else:
        return None
    if name not in {"import_module", "__import__"}:
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    value = node.args[0].value
    return value if isinstance(value, str) else None


def _concrete_robot(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "robots":
        return parts[1]
    return None


def _sibling_package(module: str, package: str) -> str | None:
    """Return ``<package>.<name>``'s name for a sibling import."""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == package:
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
    if relative[0] == "capabilities" and len(relative) > 1:
        return "capability", relative[1]
    if relative[0] == "rpent":
        return "core", ""
    return None


def _declared_imports(root: Path) -> dict[str, set[str]]:
    """Return component -> siblings it may import because it declares them."""
    try:
        components = discover_components(root)
    except InstallConfigError:
        return {}
    return {name: set(component.imports) for name, component in components.items()}


def check_top_level(root: Path) -> list[Finding]:
    """Return K1 violations."""
    findings: list[Finding] = []
    for entry in sorted(root.iterdir()):
        name = entry.name
        if name.startswith(".") or name in IGNORED_TOP_LEVEL:
            continue
        if name.endswith(".egg-info"):
            continue
        if entry.is_dir():
            if name not in ALLOWED_TOP_LEVEL:
                findings.append(
                    Finding(
                        entry,
                        0,
                        f"top-level directory {name!r} has no owner; add it to "
                        "the a_1 4.1 table before creating it",
                    )
                )
        elif not any(fnmatch(name, pattern) for pattern in ALLOWED_ROOT_FILES):
            findings.append(
                Finding(
                    entry,
                    0,
                    f"root file {name!r} is not whitelisted; move it into a "
                    "owned directory or extend the a_1 4.1 whitelist",
                )
            )
    return findings


def check_imports(root: Path) -> list[Finding]:
    """Return K4 import boundary violations under ``root``."""
    findings: list[Finding] = []
    declared_imports = _declared_imports(root)
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
        relative = path.relative_to(root).as_posix()
        for line, module in _imports(path):
            robot = _concrete_robot(module)
            if kind in {"toolkit", "capability"}:
                if module == "robots" or robot is not None:
                    label = (
                        "toolkits must not import robots"
                        if kind == "toolkit"
                        else f"capability {name!r} must not import robots"
                    )
                    findings.append(Finding(path, line, label))
                package = "toolkits" if kind == "toolkit" else "capabilities"
                sibling = _sibling_package(module, package)
                if sibling is not None and sibling != name and sibling != "_base":
                    findings.append(
                        Finding(
                            path,
                            line,
                            f"{kind} {name!r} must not import sibling "
                            f"{sibling!r}; declare a shared contract instead",
                        )
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
                            "declare it in component.toml imports when the "
                            "integration intentionally extends another slice",
                        )
                    )
            elif kind == "core":
                if relative in CORE_EXEMPTIONS:
                    continue
                if module == "toolkits" or module.startswith("toolkits."):
                    findings.append(
                        Finding(
                            path,
                            line,
                            "core must not import toolkits; pass a toolkit "
                            "through the robot slice",
                        )
                    )
                if module == "capabilities" or module.startswith("capabilities."):
                    findings.append(
                        Finding(
                            path,
                            line,
                            "core must not import capabilities; keep model "
                            "services behind the slice contract",
                        )
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


def check_core_robot_names(root: Path) -> list[Finding]:
    """Return K5 findings for robot or benchmark names in core sources."""
    names = _component_names(root / "robots")
    if not names:
        return []
    pattern = re.compile(
        r"(?<![0-9A-Za-z_])(?:%s)(?![0-9A-Za-z_])"
        % "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)),
        re.IGNORECASE,
    )
    findings: list[Finding] = []
    for path in sorted((root / "rpent").rglob("*.py")):
        if any(part in {".git", ".rpent", "__pycache__"} for part in path.parts):
            continue
        try:
            with path.open("rb") as file:
                tokens = list(tokenize.tokenize(file.readline))
        except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError):
            continue
        for token in tokens:
            if token.type not in {
                tokenize.NAME,
                tokenize.STRING,
                tokenize.COMMENT,
            }:
                continue
            match = pattern.search(token.string)
            if match is None:
                continue
            findings.append(
                Finding(
                    path,
                    token.start[0],
                    f"core names {match.group(0)!r}; move the robot or "
                    "benchmark detail into its slice",
                )
            )
    return findings


def check_lazy_slices(root: Path) -> list[Finding]:
    """Return K6 findings for slice ``__init__.py`` files that import eagerly."""
    findings: list[Finding] = []
    robots = root / "robots"
    if not robots.is_dir():
        return findings
    for path in sorted(robots.glob("*/__init__.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if _is_lazy_statement(node):
                continue
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "slice __init__.py must stay lazy; export through "
                    "__getattr__ so a missing optional dependency does not "
                    "break robot discovery",
                )
            )
    return findings


def _is_lazy_statement(node: ast.stmt) -> bool:
    """Return whether ``node`` is part of the lazy slice entry pattern."""
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        # Module docstring.
        return isinstance(node.value.value, str)
    if isinstance(node, ast.ImportFrom):
        return node.module in {"__future__", "typing", "typing_extensions"}
    if isinstance(node, (ast.Import,)):
        return False
    if isinstance(node, ast.Assign):
        return all(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    if isinstance(node, ast.FunctionDef):
        return node.name == "__getattr__"
    if isinstance(node, ast.If):
        # Type-checking imports never execute at runtime.
        return _is_type_checking(node.test) and all(
            isinstance(child, (ast.Import, ast.ImportFrom)) for child in node.body
        )
    return False


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def check_coverage(root: Path) -> list[Finding]:
    """Return K2 findings for missing or mismatched component manifests."""
    findings: list[Finding] = []
    try:
        components = discover_components(root)
    except InstallConfigError as exc:
        return [Finding(root / "component.toml", 0, str(exc))]
    declared = {component.path.resolve() for component in components.values()}
    roots = [
        (root / "robots", "robot"),
        (root / "toolkits", "toolkit"),
        (root / "capabilities", "capability"),
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


def check_role_files(root: Path) -> list[Finding]:
    """Return K2 findings for components missing their skeleton files."""
    findings: list[Finding] = []
    roots = [
        (root / "robots", "robot"),
        (root / "toolkits", "toolkit"),
        (root / "capabilities", "capability"),
    ]
    for directory, kind in roots:
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            if kind == "capability" and not any(child.glob("*.py")):
                continue
            required = REQUIRED_ROLE_FILES[kind]
            missing = [name for name in required if not (child / name).exists()]
            if not missing:
                continue
            level = WARNING if (kind, child.name) in LEGACY_COMPONENTS else ERROR
            findings.append(
                Finding(
                    child,
                    0,
                    f"{kind} {child.name!r} is missing its skeleton files: "
                    f"{', '.join(missing)}",
                    level,
                )
            )
    return findings


def check_legacy_names(root: Path) -> list[Finding]:
    """Return K3 findings for retired slice-root names."""
    findings: list[Finding] = []
    robots = root / "robots"
    if not robots.is_dir():
        return findings
    for slice_dir in sorted(robots.iterdir()):
        if not slice_dir.is_dir() or slice_dir.name.startswith((".", "_")):
            continue
        baseline = LEGACY_SLICES.get(slice_dir.name, frozenset())
        present = sorted(
            entry.name
            for entry in slice_dir.iterdir()
            if entry.name in LEGACY_SLICE_NAMES
        )
        if not present:
            continue
        if slice_dir.name in MIGRATED_SLICES:
            findings.append(
                Finding(
                    slice_dir,
                    0,
                    f"slice {slice_dir.name!r} is migrated but keeps retired "
                    f"names: {', '.join(present)}",
                )
            )
            continue
        added = [name for name in present if name not in baseline]
        if added:
            findings.append(
                Finding(
                    slice_dir,
                    0,
                    f"slice {slice_dir.name!r} added retired names "
                    f"{', '.join(added)}; use the a_1 4.2 role names instead",
                )
            )
        kept = [name for name in present if name in baseline]
        if kept:
            findings.append(
                Finding(
                    slice_dir,
                    0,
                    f"slice {slice_dir.name!r} still has {len(kept)} pre-migration "
                    f"names ({', '.join(kept)}); the a_5 migration renames them and "
                    "turns this into an error",
                    WARNING,
                )
            )
    return findings


def check_file_sizes(root: Path) -> list[Finding]:
    """Return K7 warnings for role files over their line-count limit."""
    findings: list[Finding] = []
    for directory in ("robots", "toolkits"):
        for path in sorted((root / directory).rglob("*.py")):
            limit = LINE_LIMITS.get(path.name)
            if limit is None:
                continue
            try:
                lines = sum(1 for _ in path.open(encoding="utf-8"))
            except OSError:
                continue
            if lines > limit:
                findings.append(
                    Finding(
                        path,
                        0,
                        f"{path.name} has {lines} lines (limit {limit}); "
                        "split it along the a_5 roles",
                        WARNING,
                    )
                )
    return findings


def _component_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        child.name
        for child in directory.iterdir()
        if child.is_dir() and not child.name.startswith((".", "_"))
    }


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
    findings = (
        check_top_level(root)
        + check_coverage(root)
        + check_role_files(root)
        + check_legacy_names(root)
        + check_imports(root)
        + check_core_robot_names(root)
        + check_lazy_slices(root)
        + check_file_sizes(root)
    )
    for finding in findings:
        location = (
            finding.path.relative_to(root)
            if finding.path.is_relative_to(root)
            else finding.path
        )
        suffix = f":{finding.line}" if finding.line else ""
        print(f"{location}{suffix}: {finding.level}: {finding.message}")
    errors = [finding for finding in findings if finding.level == ERROR]
    if errors:
        print(f"{len(errors)} layout violation(s)", file=sys.stderr)
        return 1
    print("layout ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
