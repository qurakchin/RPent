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
contains: the profile, the component manifests, the lock the install reads, the
override files its components apply, and the repository's ``[tool.uv]``
resolution settings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import Profile
from rpent.install.resolve import Resolution

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


#: ``[tool.uv]`` entries that do not change an installation's contents.
#: ``conflicts`` only constrains extra combinations in the generated
#: compatibility block, and ``rpent-env`` installs requirement files rather
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


def _lock_sha256(profile: Profile, root: Path, *, reproducible: bool) -> str | None:
    """Return the hash of the lock the installation read, if it read one.

    ``--dev`` and component diagnostics install from generated requirements
    instead, so they have no lock input.
    """
    if not reproducible or profile.lock is None:
        return None
    try:
        return hashlib.sha256((root / profile.lock).read_bytes()).hexdigest()
    except OSError:
        # A deleted lock makes the inputs hash change, which is exactly the
        # drift it should report.
        return None


def _override_inputs(resolution: Resolution, root: Path) -> list[dict[str, str]]:
    """Return the override files an installation applies, with their hashes."""
    entries: list[dict[str, str]] = []
    for display, path in override_files(resolution, root):
        try:
            data = path.read_bytes()
        except OSError:
            # The installer hands the file to uv, which fails on a missing
            # override; leaving it out keeps the hash true to what was read.
            continue
        entries.append({"path": display, "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def environment_dependencies(
    resolution: Resolution,
    environment: str,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return every direct requirement installed into one environment."""
    requirements: list[str] = []
    if environment == resolution.profile.name:
        if resolution.profile.core:
            requirements.extend(core_dependencies)
        requirements.extend(resolution.profile.dependencies)
    requirements.extend(resolution.dependencies_for(environment))
    return tuple(dict.fromkeys(requirements))


def render_requirements(
    resolution: Resolution,
    environment: str,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Render a stable requirements file for one environment."""
    profile = resolution.profile
    source = (
        f"a development environment for component {profile.name!r}"
        if profile.synthetic
        else f"envs/{profile.name}.toml"
    )
    lines = [
        f"# Generated by rpent-env from {source}.",
        "# Do not edit; change the profile or a component manifest and rerun",
        f"# `rpent-env install {profile.name}`.",
        f"# environment: {environment}",
    ]
    if environment == profile.name and profile.core:
        core = sorted(dict.fromkeys(core_dependencies))
        lines.append("")
        lines.append("# RPent core")
        lines.extend(core)
    if environment == profile.name:
        profile_deps = sorted(dict.fromkeys(profile.dependencies))
        if profile_deps:
            lines.append("")
            lines.append(f"# profile {profile.name}")
            lines.extend(profile_deps)
    for name in resolution.environments().get(environment, ()):
        resolved = resolution.components[name]
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
    include_dev: bool = False,
    reproducible: bool = False,
) -> dict[str, Any]:
    """Return the canonical inputs whose hash identifies an installation.

    ``root`` locates the lock and override files, and ``reproducible`` says
    whether the installation reads the lock; a ``--dev`` or component
    diagnostic installation does not, so its contents do not depend on it.
    """
    profile = resolution.profile
    components = {}
    for name, resolved in sorted(resolution.components.items()):
        components[name] = {
            "manifest_sha256": resolved.component.manifest_sha256,
            "placement": resolved.placement,
            "variant": resolved.variant,
            # A deps component can live in several environments; recording
            # one of them here would be arbitrary. Its membership lives in
            # ``environment_deps`` instead.
            **({} if resolved.component.is_deps else {"env": resolved.env}),
        }
    return {
        "schema": 1,
        # A deps component installs into every environment whose component
        # requires it, so its membership is recorded separately from the
        # single-environment ``env`` field below.
        "environment_deps": {
            environment: sorted(names)
            for environment, names in sorted(resolution.environment_deps.items())
        },
        "profile": {
            "name": profile.name,
            "python": profile.python,
            "platform": profile.platform,
            "components": components,
            "dependencies": sorted(profile.dependencies),
            "index_url": profile.index_url,
            "extra_index_urls": sorted(profile.extra_index_urls),
            "core": profile.core,
        },
        "core_dependencies": sorted(core_dependencies),
        "include_dev": include_dev,
        # The lock and the override files are install inputs that no manifest
        # hash covers: recompiling a lock or editing an override changes what a
        # reinstall would produce, so `doctor` has to be able to see it.
        "lock_sha256": _lock_sha256(profile, root, reproducible=reproducible),
        "overrides": _override_inputs(resolution, root),
        "uv_settings": read_uv_settings(root),
    }


def requirements_sha256(
    resolution: Resolution,
    *,
    root: Path,
    core_dependencies: tuple[str, ...] = (),
    include_dev: bool = False,
    reproducible: bool = False,
) -> str:
    """Hash every input that determines what the installation contains."""
    payload = json.dumps(
        requirements_inputs(
            resolution,
            root=root,
            core_dependencies=core_dependencies,
            include_dev=include_dev,
            reproducible=reproducible,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dependency_requirements_text(
    resolution: Resolution,
    environment: str,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Return only requirement lines, without comments or blank lines.

    Used by ``rpent-env lock`` to feed ``uv pip compile``.
    """
    return (
        "\n".join(
            environment_dependencies(
                resolution,
                environment,
                core_dependencies=core_dependencies,
            )
        )
        + "\n"
    )
