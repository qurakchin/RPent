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

"""Discover component manifests and install targets in a source checkout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    COMPONENT_DIRECTORIES,
    KINDS,
    Component,
    Target,
    load_component,
    load_target,
    target_from_component,
)

#: Every component root and the glob that finds it, one directory manifest per
#: component. The glob order fixes the order components are reported in.
COMPONENT_ROOTS = tuple(
    (f"{directory}/*/component.toml", kind)
    for kind, directory in COMPONENT_DIRECTORIES.items()
)
#: Kinds a component may name in ``requires``. A simulator and a model service
#: meet only in a robot target, so neither may require the other; tool and
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
    """Components and install targets available in one checkout."""

    root: Path
    components: dict[str, Component]
    targets: dict[str, Target]


def repository_root() -> Path:
    """Return the checkout that owns the manifests.

    Walking up from this module finds the checkout an editable install points
    at even when the command runs elsewhere. A wheel has no ``installs/``, so
    the current directory is the only remaining candidate; discovery then
    reports that it is not a source checkout.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "installs" / "targets").is_dir():
            return parent
    return Path.cwd()


def _is_metadata_file(path: Path) -> bool:
    """Return whether ``path`` is an AppleDouble or other dot metadata file.

    Network filesystems store macOS extended attributes as ``._<name>`` files
    next to the original, so a synced checkout can gain ``._target.toml``
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
    target, so one cannot require the other: the robot adapter is what composes
    them, and its target selects both.
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


def target_roots(root: Path) -> tuple[Path, ...]:
    """Return the directories target manifests are discovered in.

    User targets live under ``installs/targets/``; the ones that serve only
    tests and CI live under ``tests/targets/``. Every non-robot component
    directory is also an install target under its own name, so a
    single-component environment needs no file here; robots always need an
    explicit target because a robot is never installed on its own by name.
    """
    return (root / "installs" / "targets", root / "tests" / "targets")


def _targets(repo_root: Path, components: dict[str, Component]) -> dict[str, Target]:
    user_targets, test_targets = target_roots(repo_root)
    targets: dict[str, Target] = {}
    for directory in (user_targets, test_targets):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.toml")):
            if _is_metadata_file(path):
                continue
            target = load_target(path)
            previous = targets.get(target.name)
            if previous is not None:
                raise InstallConfigError(
                    f"target {target.name!r} is declared twice: "
                    f"{previous.relative_path(repo_root)} and "
                    f"{target.relative_path(repo_root)}; "
                    "test targets share the user target namespace"
                )
            _check_override_target(target, components, repo_root)
            targets[target.name] = target
    for name, component in sorted(components.items()):
        if component.kind == "robot":
            # A robot is an integration, not an install unit: it needs a target
            # file that names what to install alongside it.
            continue
        targets[name] = target_from_component(component)
    return targets


def _check_override_target(
    target: Target, components: dict[str, Component], repo_root: Path
) -> None:
    """Reject a target that reuses a component name without being its override.

    A target name must not collide with a component name, because the
    component already installs under that name. The one exception is a robot
    component's same-name override target, which exists to bind the robot to a
    composition; it must install the robot it is named after.
    """
    component = components.get(target.name)
    if component is None:
        return
    if component.kind != "robot":
        raise InstallConfigError(
            f"target {target.name!r} in {target.relative_path(repo_root)} "
            f"reuses the name of component {component.manifest_path}; "
            "non-robot components are already installable under their own "
            "name, so rename the target"
        )
    if component.name not in target.components:
        raise InstallConfigError(
            f"target {target.name!r} in {target.relative_path(repo_root)} "
            f"overrides robot component {component.manifest_path} but does "
            f"not select it; add [components.{component.name}] to the target "
            "or rename it"
        )


def discover_targets(root: Path | None = None) -> dict[str, Target]:
    """Load every target, including one synthesized per non-robot component.

    A target that reuses a component name without being a robot's override and
    an override that does not install its own robot are rejected rather than
    installed under a silently narrowed environment.
    """
    repo_root = (root or repository_root()).resolve()
    return _targets(repo_root, discover_components(repo_root))


def discover(root: Path | None = None) -> Catalog:
    """Return all components and targets in one checkout."""
    repo_root = (root or repository_root()).resolve()
    components = discover_components(repo_root)
    return Catalog(
        root=repo_root,
        components=components,
        targets=_targets(repo_root, components),
    )
