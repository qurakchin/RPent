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

"""Discover component manifests and environment profiles in a source checkout."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    Component,
    Profile,
    load_component,
    load_deps_component,
    load_profile,
)
from rpent.utils.config import get_repo_root

#: Every component root and the glob that finds it. Directory kinds read a
#: ``component.toml``; the ``deps`` kind reads one file per component.
COMPONENT_ROOTS = (
    ("robots/*/component.toml", "robot"),
    ("toolkits/*/component.toml", "toolkit"),
    ("capabilities/*/component.toml", "capability"),
    ("rpent/*/component.toml", "capability"),
    ("envs/deps/*.toml", "deps"),
)


@dataclass(frozen=True)
class Catalog:
    """Components and profiles available in one checkout."""

    root: Path
    components: dict[str, Component]
    profiles: dict[str, Profile]


def _is_metadata_file(path: Path) -> bool:
    """Return whether ``path`` is an AppleDouble or other dot metadata file.

    Network filesystems store macOS extended attributes as ``._<name>`` files
    next to the original, so a synced checkout can gain ``._profile.toml``
    entries that are not manifests.
    """
    return path.name.startswith(".")


def _component_manifests(root: Path) -> Iterable[tuple[Path, str]]:
    seen: set[Path] = set()
    for pattern, kind in COMPONENT_ROOTS:
        for manifest in sorted(root.glob(pattern)):
            if _is_metadata_file(manifest):
                continue
            resolved = manifest.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield manifest, kind


def discover_components(root: Path | None = None) -> dict[str, Component]:
    """Load every component manifest under ``root``.

    Raises:
        InstallConfigError: a manifest is invalid, duplicated, or has a kind
            that does not match the directory root it lives under.
    """
    repo_root = (root or get_repo_root()).resolve()
    components: dict[str, Component] = {}
    for manifest, expected_kind in _component_manifests(repo_root):
        if expected_kind == "deps":
            component = load_deps_component(manifest)
        else:
            component = load_component(manifest)
        if component.kind != expected_kind:
            raise InstallConfigError(
                f"{manifest}: kind {component.kind!r} does not match the "
                f"{expected_kind!r} component root"
            )
        previous = components.get(component.name)
        if previous is not None:
            raise InstallConfigError(
                f"component {component.name!r} is declared twice: "
                f"{previous.manifest_path} and {manifest}"
            )
        components[component.name] = component
    _check_conflicts(components)
    _check_deps_consumers(components)
    _check_imports(components)
    return _close_conflicts(components)


def _check_imports(components: dict[str, Component]) -> None:
    """Require ``imports`` to name a co-installed component of the same kind."""
    reverse = {
        other.name: set(other.requires)
        for other in components.values()
        if not other.is_deps
    }
    for component in components.values():
        for other in component.imports:
            target = components.get(other)
            if target is None:
                raise InstallConfigError(
                    f"{component.manifest_path}: imports references unknown "
                    f"component {other!r}"
                )
            if target.kind != component.kind:
                raise InstallConfigError(
                    f"{component.manifest_path}: imports {other!r} must name a "
                    f"{component.kind} component, not {target.kind!r}"
                )
            if other not in component.requires and component.name not in reverse[other]:
                raise InstallConfigError(
                    f"{component.manifest_path}: imports {other!r}, but neither "
                    "component requires the other; add it to requires so the "
                    "install closure includes both"
                )


def _check_deps_consumers(components: dict[str, Component]) -> None:
    """Require every deps component to serve at least two components."""
    consumers: dict[str, list[str]] = {name: [] for name in components}
    for component in components.values():
        if component.is_deps:
            continue
        for required in component.requires:
            if required in consumers:
                consumers[required].append(component.name)
    for name, component in components.items():
        if not component.is_deps:
            continue
        used_by = sorted(set(consumers[name]))
        if len(used_by) < 2:
            raise InstallConfigError(
                f"{component.manifest_path}: deps component {name!r} is required "
                f"by {', '.join(used_by) or 'no component'}; a single consumer "
                "belongs in that component's own dependencies"
            )


def _check_conflicts(components: dict[str, Component]) -> None:
    """Require every ``env_conflicts`` entry to name another known component."""
    for component in components.values():
        for other in component.env_conflicts:
            if other not in components:
                raise InstallConfigError(
                    f"{component.manifest_path}: env_conflicts references unknown "
                    f"component {other!r}"
                )
            if other == component.name:
                raise InstallConfigError(
                    f"{component.manifest_path}: env_conflicts names the component "
                    "itself"
                )


def _close_conflicts(components: dict[str, Component]) -> dict[str, Component]:
    """Return components whose ``env_conflicts`` include the mirror declaration.

    A manifest may name a conflicting component once; the effective relation is
    symmetric, so the other side reports it without editing that manifest.
    Manifests that already declare both sides keep their written order.
    """
    declared = {
        name: set(component.env_conflicts) for name, component in components.items()
    }
    for name, others in list(declared.items()):
        for other in others:
            declared[other].add(name)
    return {
        name: (
            component
            if set(component.env_conflicts) == declared[name]
            else replace(component, env_conflicts=tuple(sorted(declared[name])))
        )
        for name, component in components.items()
    }


def discover_profiles(root: Path | None = None) -> dict[str, Profile]:
    """Load every profile under ``envs/`` in ``root``.

    Raises:
        InstallConfigError: ``root`` is not a source checkout with ``envs/``.
    """
    repo_root = (root or get_repo_root()).resolve()
    envs = repo_root / "envs"
    if not envs.is_dir():
        raise InstallConfigError(
            f"{envs} does not exist; environment profiles ship with the source "
            "checkout, so run rpent-env from the repository root or reinstall "
            "RPent in editable mode (pip install -e .)"
        )
    profiles: dict[str, Profile] = {}
    for path in sorted(envs.glob("*.toml")):
        if _is_metadata_file(path):
            continue
        profile = load_profile(path)
        if profile.name in profiles:
            raise InstallConfigError(
                f"profile {profile.name!r} is declared twice: "
                f"{profiles[profile.name].path} and {path}"
            )
        profiles[profile.name] = profile
    return profiles


def discover(root: Path | None = None) -> Catalog:
    """Return all components and profiles in one checkout."""
    repo_root = (root or get_repo_root()).resolve()
    return Catalog(
        root=repo_root,
        components=discover_components(repo_root),
        profiles=discover_profiles(repo_root),
    )
