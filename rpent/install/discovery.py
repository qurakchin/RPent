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

"""Discover the component manifests declared by a source checkout.

A checkout has no separate install-target files: every component is installable
under its own name, and the components a robot runs with are named by its
``requires``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    COMPONENT_DIRECTORIES,
    KINDS,
    MINIMAL_ENVIRONMENT,
    Component,
    environment_name,
    load_component,
)

#: Every component root and the glob that finds it, one directory manifest per
#: component. The glob order fixes the order components are reported in.
COMPONENT_ROOTS = tuple(
    (f"{directory}/*/component.toml", kind)
    for kind, directory in COMPONENT_DIRECTORIES.items()
)
#: Kinds a component may name in ``requires``. A simulator and a model service
#: meet only in a robot environment, so neither may require the other; tool and
#: infra components stay below both. Only a robot composes the rest.
REQUIRED_KINDS = {
    "robot": frozenset(KINDS),
    "sim": frozenset({"tool", "infra"}),
    "model": frozenset({"tool", "infra"}),
    "tool": frozenset({"tool", "infra"}),
    "infra": frozenset({"tool", "infra"}),
}


@dataclass(frozen=True)
class Catalog:
    """The components available in one checkout."""

    root: Path
    components: dict[str, Component]


def repository_root() -> Path:
    """Return the checkout that owns the manifests.

    Walking up from this module finds the checkout an editable install points
    at even when the command runs elsewhere. A wheel has no component roots, so
    the current directory is the only remaining candidate; discovery then
    reports that it is not a source checkout.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "components").is_dir() and (parent / "robots").is_dir():
            return parent
    return Path.cwd()


def _is_metadata_file(path: Path) -> bool:
    """Return whether ``path`` is an AppleDouble or other dot metadata file.

    Network filesystems store macOS extended attributes as ``._<name>`` files
    next to the original, so a synced checkout can gain ``._component.toml``
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
        InstallConfigError: a manifest is invalid, duplicated, or has a name
            that does not match the root it lives under.
    """
    repo_root = (root or repository_root()).resolve()
    components: dict[str, Component] = {}
    for manifest, kind in _component_manifests(repo_root):
        component = load_component(manifest, kind)
        previous = components.get(component.name)
        if previous is not None:
            raise InstallConfigError(
                f"component {component.name!r} is declared twice: "
                f"{previous.manifest_path} and {manifest}"
            )
        components[component.name] = component
    _check_conflicts(components)
    _check_requires(components)
    _check_imports(components)
    return components


def _check_requires(components: dict[str, Component]) -> None:
    """Reject a ``requires`` edge that crosses the kind layering.

    Every required component must exist and belong to a kind the requiring one
    may build on. A simulator and a model service only meet inside a robot
    environment, so one cannot require the other: the robot adapter is what
    composes them, and its ``requires`` names both.
    """
    for component in components.values():
        allowed = REQUIRED_KINDS[component.kind]
        for required in component.requires:
            other = components.get(required)
            if other is None:
                raise InstallConfigError(
                    f"{component.manifest_path}: requires unknown component "
                    f"{required!r}"
                )
            if other.kind not in allowed:
                raise InstallConfigError(
                    f"{component.manifest_path}: {component.kind} "
                    f"{component.name!r} requires {other.kind} {other.name!r}; "
                    f"a {component.kind} component may require only "
                    f"{', '.join(sorted(allowed))} components"
                )


def _check_imports(components: dict[str, Component]) -> None:
    """Allow ``imports`` on robot slices, naming a co-installed robot.

    Every other component shares a contract with its neighbors instead of
    importing their modules, so an ``imports`` entry on one is a manifest
    error rather than a boundary the layout check has to honour.
    """
    reverse = {other.name: set(other.requires) for other in components.values()}
    for component in components.values():
        for other in component.imports:
            if component.kind != "robot":
                raise InstallConfigError(
                    f"{component.manifest_path}: imports is only for robot "
                    f"slices; {component.kind} components share a contract "
                    "instead of importing each other"
                )
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


def _check_conflicts(components: dict[str, Component]) -> None:
    """Require every ``env_conflicts`` entry to name another known component.

    The relation is read symmetrically by resolution, so a manifest names one
    side of a conflict and the other side needs no edit.
    """
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


def environment_names(components: dict[str, Component]) -> tuple[str, ...]:
    """Return every environment the checkout can install by name.

    ``minimal`` is the core-only environment; every component installs under
    its own name. A composition of several components is addressed by the
    sorted join of their names and has no separate entry here.
    """
    return (MINIMAL_ENVIRONMENT, *sorted(components))


def requested_components(
    name: str, components: dict[str, Component]
) -> tuple[str, ...]:
    """Return the components the environment ``name`` requests.

    ``minimal`` requests none, which is the core-only environment. Every
    component is an environment of its own, and a composition of several is
    named by their sorted join, so ``install a b`` and ``check a+b`` address one
    environment.
    """
    if name == MINIMAL_ENVIRONMENT:
        return ()
    names = tuple(part for part in name.split("+") if part)
    if not names or any(part not in components for part in names):
        known = ", ".join(environment_names(components))
        raise InstallConfigError(f"unknown environment {name!r}; known: {known}")
    canonical = environment_name(names)
    if canonical != name:
        raise InstallConfigError(
            f"environment {name!r} is not in canonical order; name it {canonical!r}"
        )
    return names


def discover(root: Path | None = None) -> Catalog:
    """Return all components in one checkout."""
    repo_root = (root or repository_root()).resolve()
    return Catalog(root=repo_root, components=discover_components(repo_root))
