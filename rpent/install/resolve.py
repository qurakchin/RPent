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

"""Resolve a profile into environments, dependencies, and configuration errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpent.install.discovery import Catalog
from rpent.install.manifest import Component, Profile, Selection

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

# ``packaging`` parses requirement strings and is imported where that happens,
# not at module import. Manifest discovery (``scripts/env_matrix.py``) imports
# this module through ``rpent.install`` and must run in a checkout that has no
# third-party packages installed; every install path still needs packaging.


@dataclass(frozen=True)
class ResolvedComponent:
    """One component placed by a profile."""

    component: Component
    placement: str
    variant: str | None
    env: str | None

    @property
    def name(self) -> str:
        """Return the component name."""
        return self.component.name

    def dependencies(self) -> tuple[str, ...]:
        """Return direct dependencies including the selected variant."""
        return self.component.dependencies_for(self.variant)


@dataclass
class Resolution:
    """The environments and diagnostics produced by one profile."""

    profile: Profile
    components: dict[str, ResolvedComponent] = field(default_factory=dict)
    #: Environment name -> deps components installed there because a consumer
    #: in that environment requires them. A deps component has no placement of
    #: its own, so it may appear in more than one environment.
    environment_deps: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether static checks passed."""
        return not self.errors

    def environments(self) -> dict[str, tuple[str, ...]]:
        """Return environment name to component names, excluding remote ones."""
        groups: dict[str, list[str]] = {self.profile.name: []}
        for resolved in self.components.values():
            if resolved.component.is_deps:
                continue
            if resolved.placement == "remote" or resolved.env is None:
                continue
            groups.setdefault(resolved.env, []).append(resolved.name)
        for environment, names in self.environment_deps.items():
            groups.setdefault(environment, []).extend(names)
        return {name: tuple(sorted(names)) for name, names in groups.items()}

    def nonempty_environments(self) -> dict[str, tuple[str, ...]]:
        """Return environments that contain at least one component."""
        return {name: names for name, names in self.environments().items() if names}

    def main_components(self) -> dict[str, ResolvedComponent]:
        """Return components installed into the profile's main environment."""
        return {
            name: resolved
            for name, resolved in self.components.items()
            if resolved.placement == "in-env" and not resolved.component.is_deps
        }

    def main_deps(self) -> dict[str, ResolvedComponent]:
        """Return deps components grouped into the profile's main environment."""
        names = self.environment_deps.get(self.profile.name, [])
        return {name: self.components[name] for name in names}

    def main_installed(self) -> dict[str, ResolvedComponent]:
        """Return every component installed into the profile's main environment.

        This is what the environment must be able to import: components with
        code and the deps groups their consumers require.
        """
        return {**self.main_components(), **self.main_deps()}

    def external_components(self) -> dict[str, ResolvedComponent]:
        """Return components installed into named external environments.

        A deps component installs with its consumers, so it is not a service
        with an endpoint of its own even when a consumer is external.
        """
        return {
            name: resolved
            for name, resolved in self.components.items()
            if resolved.placement == "external-env" and not resolved.component.is_deps
        }

    def dependencies_for(self, environment: str) -> tuple[str, ...]:
        """Return the direct dependencies of one environment."""
        requirements: list[str] = []
        for name in self.environments().get(environment, ()):
            requirements.extend(self.components[name].dependencies())
        return tuple(requirements)


def _canonical(value: str) -> tuple[str, SpecifierSet, str] | None:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name

    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None
    if requirement.marker is not None:
        # Marker-scoped pins select different wheels per interpreter/platform
        # (for example per-version pxd wheels); the resolver decides which one
        # applies, so they are not contradictory declarations.
        return None
    url = str(requirement.url) if requirement.url else ""
    return (
        canonicalize_name(requirement.name),
        requirement.specifier,
        url,
    )


def _owner_pin(value: str) -> tuple[str, str] | None:
    """Return ``(package, pin)`` for an exact pin or a URL requirement.

    Ranges and unpinned requirements compose, so they are not owners: whether
    they resolve together is uv's decision (``rpent-env check --resolve``).
    """
    identity = _canonical(value)
    if identity is None:
        return None
    package, specifier, url = identity
    if url:
        return package, url
    if len(specifier) != 1:
        return None
    item = next(iter(specifier))
    if item.operator not in {"==", "==="} or item.version.endswith(".*"):
        return None
    return package, f"{item.operator}{item.version}"


def _pin_conflicts(
    requirements: list[tuple[str, str]],
) -> dict[str, list[tuple[str, str]]]:
    """Return package -> [(component, pin)] when exact pins disagree.

    Sampling version boundaries to test range overlap reported false conflicts
    at post-release and pre-release edges (``>1.0`` vs ``<1.0.1`` is satisfied
    by ``1.0.post1``), so this check stays syntactic: two different exact pins
    or URLs for one package in one environment, and no more.
    """
    pins: dict[str, list[tuple[str, str]]] = {}
    for component_name, value in requirements:
        owner = _owner_pin(value)
        if owner is None:
            continue
        package, pin = owner
        pins.setdefault(package, []).append((component_name, pin))
    conflicts: dict[str, list[tuple[str, str]]] = {}
    for package, entries in sorted(pins.items()):
        if len({pin for _, pin in entries}) < 2:
            continue
        conflicts[package] = sorted(set(entries))
    return conflicts


def _dependency_pins(component: ResolvedComponent) -> dict[str, str]:
    """Return package -> pin for one component's direct requirements."""
    identities = (_canonical(value) for value in component.dependencies())
    return {
        identity[0]: str(identity[1]) or identity[2]
        for identity in identities
        if identity is not None
    }


def _format_conflict(
    left: ResolvedComponent,
    right: ResolvedComponent,
    *,
    environment: str,
) -> str:
    left_deps = _dependency_pins(left)
    right_deps = _dependency_pins(right)
    details = [
        f"  {left.name}: {package} {left_deps[package]}"
        f" / {right.name}: {package} {right_deps[package]}"
        for package in sorted(set(left_deps) & set(right_deps))
        if left_deps[package] != right_deps[package]
    ]
    if not details:
        details = [
            f"  {left.name} and {right.name} declare env_conflicts"
            " (a transitive version incompatibility)"
        ]
    movable = next(
        (
            candidate
            for candidate in (right, left)
            if "external-env" in candidate.component.placements
        ),
        None,
    )
    suggestion = (
        f"  option 1: move {movable.name} to external-env in envs/{environment}.toml"
        if movable is not None
        else f"  option 1: install {right.name} in a separate environment"
    )
    return (
        f"profile {environment!r} places {left.name!r} and {right.name!r} "
        "in the same environment, but they conflict\n"
        + "\n".join(details)
        + f"\n{suggestion}\n"
        f"  option 2: install without {right.name}: "
        f"rpent-env install {environment}"
    )


def _check_component_range(resolved: ResolvedComponent, profile: Profile) -> list[str]:
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    errors: list[str] = []
    component = resolved.component
    if component.python is not None:
        try:
            supported = SpecifierSet(component.python)
        except InvalidSpecifier as exc:
            errors.append(
                f"{component.manifest_path}: invalid python range "
                f"{component.python!r}: {exc}"
            )
        else:
            if not supported.contains(profile.python, prereleases=True):
                errors.append(
                    f"component {component.name!r} requires Python "
                    f"{component.python}, but profile {profile.name!r} uses "
                    f"{profile.python}"
                )
    if component.platforms and profile.platform not in component.platforms:
        errors.append(
            f"component {component.name!r} supports "
            f"{', '.join(component.platforms)}, but profile "
            f"{profile.name!r} targets {profile.platform}"
        )
    return errors


def resolve(
    profile: Profile,
    catalog: Catalog,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> Resolution:
    """Place the profile's components, compute closure, and report conflicts."""
    resolution = Resolution(profile=profile)
    selections = dict(profile.components)
    for name in sorted(selections):
        if name not in catalog.components:
            resolution.errors.append(
                f"profile {profile.name!r} references unknown component {name!r}; "
                f"known components: {', '.join(sorted(catalog.components))}"
            )
        elif catalog.components[name].is_deps:
            resolution.errors.append(
                f"profile {profile.name!r} selects deps component {name!r}; deps "
                "components are installed by the components that require them, so "
                "remove the [components] entry and add "
                f"'requires = [\"{name}\"]' to a consuming component"
            )
    pending = [
        name
        for name in sorted(selections)
        if name in catalog.components and not catalog.components[name].is_deps
    ]
    placed: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in placed:
            continue
        placed.add(name)
        component = catalog.components[name]
        selection = selections.get(name)
        variant = selection.variant if selection is not None else None
        if variant is None:
            variant = component.default_variant
        if variant is None and component.variant_required:
            resolution.errors.append(
                f"component {name!r} requires a variant; add "
                f"'variant = \"...\"' under [components.{name}] in "
                f"envs/{profile.name}.toml; expected one of "
                f"{', '.join(sorted(component.optional))}"
            )
        elif variant is not None and variant not in component.optional:
            resolution.errors.append(
                f"component {name!r} has no optional group {variant!r}; "
                f"expected one of {', '.join(sorted(component.optional)) or '<none>'}"
            )
            variant = None
        placement = (
            selection.placement
            if selection is not None and selection.placement is not None
            else component.default_placement
        )
        if placement not in component.placements:
            resolution.errors.append(
                f"component {name!r} cannot use placement {placement!r}; "
                f"allowed: {', '.join(component.placements)}"
            )
            placement = component.default_placement
        if placement == "external-env":
            env = (
                selection.profile
                if selection is not None and selection.profile is not None
                else component.name
            )
            external = catalog.profiles.get(env)
            if env == profile.name:
                resolution.errors.append(
                    f"component {name!r} cannot use the profile's own environment "
                    f"{env!r} as its external environment"
                )
            elif external is None:
                resolution.errors.append(
                    f"component {name!r} uses external environment {env!r}, but "
                    f"envs/{env}.toml does not exist; add the profile or set "
                    f"'env' to an existing one"
                )
            elif name not in external.components:
                resolution.errors.append(
                    f"external environment {env!r} does not install component "
                    f"{name!r}; add [components.{name}] to envs/{env}.toml"
                )
        elif placement == "in-env":
            env = profile.name
        else:
            env = None
        resolution.components[name] = ResolvedComponent(
            component=component,
            placement=placement,
            variant=variant,
            env=env,
        )
        for required in component.requires:
            if required not in catalog.components:
                resolution.errors.append(
                    f"component {name!r} requires unknown component {required!r}"
                )
                continue
            if catalog.components[required].is_deps:
                if env is None:
                    resolution.errors.append(
                        f"component {name!r} requires deps component {required!r} "
                        "but is placed remotely; deps components install with the "
                        "environment of the component that requires them"
                    )
                    continue
                names = resolution.environment_deps.setdefault(env, [])
                if required not in names:
                    names.append(required)
                # A deps component can live in several environments, but the
                # map above records each membership. Keep the first resolved
                # record so the placement does not depend on consumer order.
                resolution.components.setdefault(
                    required,
                    ResolvedComponent(
                        component=catalog.components[required],
                        placement=placement,
                        variant=None,
                        env=env,
                    ),
                )
                continue
            if required not in selections:
                selections[required] = Selection()
            pending.append(required)

    for resolved in resolution.components.values():
        resolution.errors.extend(_check_component_range(resolved, profile))

    for environment, names in resolution.environments().items():
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                left = resolution.components[left_name]
                right = resolution.components[right_name]
                if (
                    right_name in left.component.env_conflicts
                    or left_name in right.component.env_conflicts
                ):
                    resolution.errors.append(
                        _format_conflict(left, right, environment=environment)
                    )
        requirements = [
            (name, requirement)
            for name in names
            for requirement in resolution.components[name].dependencies()
        ]
        if environment == profile.name:
            requirements.extend(
                (profile.name, requirement) for requirement in core_dependencies
            )
            requirements.extend(
                (profile.name, requirement) for requirement in profile.dependencies
            )
        for package, pins in _pin_conflicts(requirements).items():
            lines = "\n".join(f"  {owner}: {package} {pin}" for owner, pin in pins)
            resolution.errors.append(
                f"profile {profile.name!r} has conflicting pins for {package!r} "
                f"in environment {environment!r}\n{lines}"
            )
    resolution.errors = sorted(dict.fromkeys(resolution.errors))
    return resolution
