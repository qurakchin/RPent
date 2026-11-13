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

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from rpent.install.discovery import Catalog
from rpent.install.manifest import Component, Profile, Selection


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
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether static checks passed."""
        return not self.errors

    def environments(self) -> dict[str, tuple[str, ...]]:
        """Return environment name to component names, excluding remote ones."""
        groups: dict[str, list[str]] = {self.profile.name: []}
        for resolved in self.components.values():
            if resolved.placement == "remote" or resolved.env is None:
                continue
            groups.setdefault(resolved.env, []).append(resolved.name)
        return {name: tuple(sorted(names)) for name, names in groups.items()}

    def nonempty_environments(self) -> dict[str, tuple[str, ...]]:
        """Return environments that contain at least one component."""
        return {name: names for name, names in self.environments().items() if names}

    def main_components(self) -> dict[str, ResolvedComponent]:
        """Return components installed into the profile's main environment."""
        return {
            name: resolved
            for name, resolved in self.components.items()
            if resolved.placement == "in-env"
        }

    def external_components(self) -> dict[str, ResolvedComponent]:
        """Return components installed into named external environments."""
        return {
            name: resolved
            for name, resolved in self.components.items()
            if resolved.placement == "external-env"
        }

    def dependencies_for(self, environment: str) -> tuple[str, ...]:
        """Return the direct dependencies of one environment."""
        requirements: list[str] = []
        for name in self.environments().get(environment, ()):
            requirements.extend(self.components[name].dependencies())
        return tuple(requirements)


def _canonical(value: str) -> tuple[str, SpecifierSet, str] | None:
    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None
    if requirement.marker is not None:
        # Marker-scoped pins select different wheels per interpreter/platform
        # (for example the cp310-cp312 Franka wheels); the resolver decides
        # which one applies, so they are not contradictory declarations.
        return None
    url = str(requirement.url) if requirement.url else ""
    return (
        canonicalize_name(requirement.name),
        requirement.specifier,
        url,
    )


def _candidates(*specifiers: SpecifierSet) -> set[Version]:
    """Return boundary versions to test whether two specifier sets overlap."""
    values: set[Version] = set()
    for specifier in specifiers:
        for item in specifier:
            raw = item.version.rstrip("*").rstrip(".")
            try:
                version = Version(raw)
            except InvalidVersion:
                continue
            values.add(version)
            values.add(Version(f"{version.major}.{version.minor}.{version.micro + 1}"))
            values.add(Version(f"{version.major}.{version.minor + 1}"))
    return values


def _compatible(
    left: tuple[SpecifierSet, str], right: tuple[SpecifierSet, str]
) -> bool:
    """Return whether two pins can select the same package version."""
    left_specifier, left_url = left
    right_specifier, right_url = right
    if left_url or right_url:
        return left_url == right_url
    if not len(left_specifier) or not len(right_specifier):
        return True
    candidates = _candidates(left_specifier, right_specifier)
    if not candidates:
        return True
    return any(
        left_specifier.contains(version, prereleases=True)
        and right_specifier.contains(version, prereleases=True)
        for version in candidates
    )


def _pin_conflicts(
    requirements: list[tuple[str, str]],
) -> dict[str, list[tuple[str, str]]]:
    """Return package -> [(component, pin)] for contradictory pins."""
    pins: dict[str, list[tuple[str, SpecifierSet, str]]] = {}
    for component_name, value in requirements:
        identity = _canonical(value)
        if identity is None:
            continue
        package, specifier, url = identity
        if not specifier and not url:
            continue
        pins.setdefault(package, []).append((component_name, specifier, url))
    conflicts: dict[str, list[tuple[str, str]]] = {}
    for package, entries in sorted(pins.items()):
        contradictory = False
        for index, (_, left_spec, left_url) in enumerate(entries):
            for _, right_spec, right_url in entries[index + 1 :]:
                if not _compatible((left_spec, left_url), (right_spec, right_url)):
                    contradictory = True
                    break
            if contradictory:
                break
        if not contradictory:
            continue
        seen: set[tuple[str, str]] = set()
        for component_name, specifier, url in entries:
            pin = str(specifier) or url
            seen.add((component_name, pin))
        conflicts[package] = sorted(seen)
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
    pending = [name for name in sorted(selections) if name in catalog.components]
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
                selection.env
                if selection is not None and selection.env is not None
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
