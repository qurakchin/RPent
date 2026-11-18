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

"""Render deterministic requirements files and installation input hashes.

An installation is identified by the hash of every input that decides what it
contains: the target, the component manifests, the lock the install reads, the
override files its components apply, and the repository's ``[tool.uv]``
resolution settings. Requirement files are hashed by the lines uv reads, so
editing a comment does not make an installation look stale.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import Target
from rpent.install.resolve import Resolution

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


#: Identifies the layout of :func:`requirements_inputs`. Bump it when a key
#: changes meaning or the repository layout moves the files the inputs name, not
#: merely when one is added: ``doctor`` uses it to tell an installation recorded
#: by an older input mode from one whose inputs drifted.
REQUIREMENTS_SCHEMA = 7

#: ``[tool.uv]`` entries that do not change an installation's contents.
#: ``conflicts`` only constrains extra combinations in the generated
#: compatibility block, and ``rpent-install`` installs requirement files rather
#: than extras.
_UV_IGNORED_SETTINGS = ("conflicts",)


def read_core_dependencies(root: Path) -> tuple[str, ...]:
    """Return ``[project].dependencies`` from the checkout's pyproject.toml."""
    path = root / "pyproject.toml"
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstallConfigError(
            f"{path}: cannot read core dependencies: {exc}"
        ) from exc
    project = data.get("project")
    if not isinstance(project, dict):
        raise InstallConfigError(f"{path}: missing [project] table")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) and item for item in dependencies
    ):
        raise InstallConfigError(f"{path}: [project].dependencies must be strings")
    return tuple(dependencies)


def read_uv_settings(root: Path) -> dict[str, Any]:
    """Return the ``[tool.uv]`` settings that apply to installs in this checkout.

    ``uv`` reads these settings from the project it runs in, so they decide how
    a requirement file resolves. The generated ``conflicts`` list is excluded:
    it constrains extra combinations, which the installer does not use.
    """
    path = root / "pyproject.toml"
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstallConfigError(f"{path}: cannot read [tool.uv]: {exc}") from exc
    tool = data.get("tool")
    settings = tool.get("uv") if isinstance(tool, dict) else None
    if not isinstance(settings, dict):
        return {}
    return {
        key: value for key, value in settings.items() if key not in _UV_IGNORED_SETTINGS
    }


def override_files(resolution: Resolution, root: Path) -> list[tuple[str, Path]]:
    """Return ``(display, path)`` for every override in the main environment.

    ``display`` is relative to ``root`` while the file lives in the checkout,
    so an installation fingerprint does not depend on where the checkout is.
    """
    files: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for resolved in resolution.main_installed().values():
        for override in resolved.component.overrides:
            path = override if override.is_absolute() else root / override
            if path in seen:
                continue
            seen.add(path)
            display = (
                str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            )
            files.append((display, path))
    # The fingerprint hashes this list, so its order must not depend on the
    # order components were resolved in.
    files.sort(key=lambda entry: entry[0])
    return files


def read_requirement_text(path: Path) -> str | None:
    """Return the text of a requirement file, or ``None`` when it is unreadable.

    A missing or unreadable file is reported as absent so callers can treat it
    as a changed input. A file that is not UTF-8 raises instead: uv rejects it
    too, and hashing bytes nobody can resolve would hide the real problem
    behind a drift report.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InstallConfigError(
            f"{path}: requirement file is not UTF-8: {exc}"
        ) from exc
    except OSError:
        return None


def _requirement_lines_sha256(text: str) -> str:
    """Hash the lines of a requirement file that a resolver reads.

    Blank lines and comments do not change a resolution, so editing them must
    not make an installation look stale. Every other line is hashed as written,
    because a changed version, marker, URL, or option does change it.
    """
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _lock_sha256(target: Target, root: Path) -> str | None:
    """Return the hash of the lock the installation read."""
    text = read_requirement_text(target.lock_file(root))
    if text is None:
        # A deleted lock makes the inputs hash change, which is exactly the
        # drift it should report.
        return None
    return _requirement_lines_sha256(text)


def _override_inputs(resolution: Resolution, root: Path) -> list[dict[str, str]]:
    """Return the override files an installation applies, with their hashes."""
    entries: list[dict[str, str]] = []
    for display, path in override_files(resolution, root):
        text = read_requirement_text(path)
        if text is None:
            # The installer hands the file to uv, which fails on a missing
            # override; leaving it out keeps the hash true to what was read.
            continue
        entries.append({"path": display, "sha256": _requirement_lines_sha256(text)})
    return entries


def installed_dependencies(
    resolution: Resolution,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return every direct requirement installed into the target's environment."""
    target = resolution.target
    requirements: list[str] = []
    if target.core:
        requirements.extend(core_dependencies)
    requirements.extend(target.dependencies)
    for name in sorted(resolution.main_installed()):
        requirements.extend(resolution.components[name].dependencies())
    return tuple(dict.fromkeys(requirements))


def render_requirements(
    resolution: Resolution,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Render a stable requirements file for the target's environment."""
    target = resolution.target
    lines = [
        f"# Generated by rpent-install from {target.relative_path}.",
        "# Do not edit; change the target or a component manifest and rerun",
        f"# `rpent-install install {target.name}`.",
        f"# target: {target.name}",
    ]
    if target.core:
        core = sorted(dict.fromkeys(core_dependencies))
        lines.append("")
        lines.append("# RPent core")
        lines.extend(core)
    target_deps = sorted(dict.fromkeys(target.dependencies))
    if target_deps:
        lines.append("")
        lines.append(f"# target {target.name}")
        lines.extend(target_deps)
    for name, resolved in sorted(resolution.main_installed().items()):
        dependencies = sorted(dict.fromkeys(resolved.dependencies()))
        if not dependencies:
            continue
        lines.append("")
        label = name if resolved.variant is None else f"{name} ({resolved.variant})"
        lines.append(f"# component {label}")
        lines.extend(dependencies)
    return "\n".join(lines) + "\n"


def requirements_inputs(
    resolution: Resolution,
    *,
    root: Path,
    core_dependencies: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the canonical inputs whose hash identifies an installation.

    ``root`` locates the lock and override files. Every installation reads its
    target's lock, so the lock is always one of the inputs.
    """
    # Override paths are recorded relative to ``root``. Resolving it here makes
    # that relative form independent of how the caller spelled the checkout.
    root = root.resolve()
    target = resolution.target
    components = {}
    for name, resolved in sorted(resolution.components.items()):
        components[name] = {
            "manifest_sha256": resolved.component.manifest_sha256,
            "placement": resolved.placement,
            "variant": resolved.variant,
        }
    return {
        "schema": REQUIREMENTS_SCHEMA,
        "target": {
            "name": target.name,
            "python": target.python,
            # The glibc baseline decides which wheel tags uv may select, so two
            # installations that differ only here are different environments.
            "manylinux": target.manylinux,
            "components": components,
            "dependencies": sorted(target.dependencies),
            "index_url": target.index_url,
            "extra_index_urls": sorted(target.extra_index_urls),
            "core": target.core,
        },
        "core_dependencies": sorted(core_dependencies),
        # The lock and the override files are install inputs that no manifest
        # hash covers: recompiling a lock or editing an override changes what a
        # reinstall would produce, so `doctor` has to be able to see it.
        "lock_sha256": _lock_sha256(target, root),
        "overrides": _override_inputs(resolution, root),
        "uv_settings": read_uv_settings(root),
    }


def requirements_sha256(
    resolution: Resolution,
    *,
    root: Path,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Hash every input that determines what the installation contains."""
    payload = json.dumps(
        requirements_inputs(
            resolution,
            root=root,
            core_dependencies=core_dependencies,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
