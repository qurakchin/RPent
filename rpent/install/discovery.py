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
from rpent.install.manifest import Component, Profile, load_component, load_profile
from rpent.utils.config import get_repo_root

#: Every component root, the expected kind, and the glob that finds it.
COMPONENT_ROOTS = (
    ("robots/*/component.toml", "robot"),
    ("toolkits/*/component.toml", "toolkit"),
    ("rpent/robots/components/*/component.toml", "capability"),
    ("rpent/*/component.toml", "capability"),
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
    return _close_conflicts(components)


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
    """Load every profile under ``envs/`` in ``root``."""
    repo_root = (root or get_repo_root()).resolve()
    profiles: dict[str, Profile] = {}
    for path in sorted((repo_root / "envs").glob("*.toml")):
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
