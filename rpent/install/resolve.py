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

"""Resolve a target into environments, dependencies, and configuration errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpent.install.discovery import Catalog
from rpent.install.manifest import (
    PYTHON_MINORS,
    Component,
    Selection,
    Target,
    python_specifier,
)

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

# ``packaging`` parses requirement strings and is imported where that happens,
# not at module import. ``tests.tooling.matrix`` imports this module through
# ``rpent.install`` and must run in a checkout that has no third-party packages
# installed; every install path still needs packaging.


@dataclass(frozen=True)
class ResolvedComponent:
    """One component installed by a target."""

    component: Component
    variant: str | None

    @property
    def name(self) -> str:
        """Return the component name."""
        return self.component.name

    def dependencies(self) -> tuple[str, ...]:
        """Return direct dependencies including the selected variant."""
        return self.component.dependencies_for(self.variant)


@dataclass
class Resolution:
    """The components and diagnostics produced by one target."""

    target: Target
    components: dict[str, ResolvedComponent] = field(default_factory=dict)
    #: Deps components pulled in by a consumer installed in this environment.
    deps: list[str] = field(default_factory=list)
    #: Concrete Python minor the target resolves to, newest supported first.
    python: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether static checks passed."""
        return not self.errors

    def main_components(self) -> dict[str, ResolvedComponent]:
        """Return components installed into the target's environment."""
        return {
            name: resolved
            for name, resolved in self.components.items()
            if not resolved.component.is_deps
        }

    def main_deps(self) -> dict[str, ResolvedComponent]:
        """Return the deps components installed with this environment."""
        return {name: self.components[name] for name in self.deps}

    def main_installed(self) -> dict[str, ResolvedComponent]:
        """Return every component installed into the target's environment.

        This is what the environment must be able to import: components with
        code and the deps groups their consumers require.
        """
        return {**self.main_components(), **self.main_deps()}


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
    they resolve together is uv's decision (``python -m tests.tooling.check --resolve``).
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


def _override_packages(component: Component) -> set[str]:
    """Return the packages a component's override files constrain.

    Marker-scoped lines select different constraints per target, so the
    resolver decides which one applies and they are not compared, the same rule
    the pin check follows. An unreadable or unparsable file is left to uv,
    which reports it when it applies the override.
    """
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name

    packages: set[str] = set()
    for path in component.overrides:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            try:
                requirement = Requirement(value)
            except InvalidRequirement:
                continue
            if requirement.marker is None:
                packages.add(canonicalize_name(requirement.name))
    return packages


def _override_conflicts(resolution: Resolution) -> list[str]:
    """Return errors for packages two components override at once.

    uv merges every component's override into one resolution, so two files
    constraining the same package leave the winner to file order. Report the
    pair and let the components own their constraints or share one file.
    """
    owners: dict[str, list[str]] = {}
    for name, resolved in sorted(resolution.main_installed().items()):
        for package in _override_packages(resolved.component):
            owners.setdefault(package, []).append(name)
    errors: list[str] = []
    for package, names in sorted(owners.items()):
        if len(names) < 2:
            continue
        errors.append(
            f"components {', '.join(repr(name) for name in names)} both override "
            f"{package!r} in target {resolution.target.name!r}; move the "
            "constraint into the component that needs it or merge the override "
            "files"
        )
    return errors


def _target_duplicate_dependencies(resolution: Resolution) -> list[str]:
    """Return errors for target dependencies a component already declares.

    A target's ``dependencies`` carry only packages no component in its
    closure owns; repeating a component's requirement hides which component
    owns the version and breaks the single-owner rule.
    """
    target = resolution.target
    if not target.dependencies:
        return []
    declared = {
        identity[0]
        for identity in map(_canonical, target.dependencies)
        if identity is not None
    }
    errors: list[str] = []
    for name, resolved in sorted(resolution.main_installed().items()):
        owned = {
            identity[0]
            for identity in map(_canonical, resolved.dependencies())
            if identity is not None
        }
        for package in sorted(declared & owned):
            errors.append(
                f"target {target.name!r} lists {package!r} in its own "
                f"dependencies, but component {name!r} already requires it; "
                "keep the requirement where its owner declares it"
            )
    return errors


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
    target: str,
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
    return (
        f"target {target!r} places {left.name!r} and {right.name!r} "
        "in the same environment, but they conflict\n"
        + "\n".join(details)
        + f"\n  split {left.name} and {right.name} into separate targets and "
        "connect them by endpoint"
    )


def _choose_python(
    target: Target,
    components: list[ResolvedComponent],
    errors: list[str],
    display: str,
) -> str | None:
    """Return the newest supported Python minor every constraint accepts.

    The target's request and each component's range are both constraints. A
    target that writes ``3.11`` pins the minor; a target that writes
    ``>=3.10,<3.13`` lets the resolver pick the newest of :data:`PYTHON_MINORS`
    that all components accept.
    """
    from packaging.specifiers import InvalidSpecifier

    try:
        requested = python_specifier(target.python)
    except InvalidSpecifier as exc:
        errors.append(f"{display}: invalid python request {target.python!r}: {exc}")
        return None
    ranges: list[tuple[str, SpecifierSet]] = []
    for resolved in components:
        component = resolved.component
        if component.python is None:
            continue
        try:
            ranges.append((component.name, python_specifier(component.python)))
        except InvalidSpecifier as exc:
            errors.append(
                f"{component.manifest_path}: invalid python range "
                f"{component.python!r}: {exc}"
            )
    for minor in PYTHON_MINORS:
        if not requested.contains(minor, prereleases=True):
            continue
        rejected = [
            name
            for name, supported in ranges
            if not supported.contains(minor, prereleases=True)
        ]
        if not rejected:
            return minor
    details = "\n".join(
        f"  {name}: Python {supported}"
        for name, supported in sorted(ranges, key=lambda item: item[0])
    )
    errors.append(
        f"target {target.name!r} requests Python {target.python}, but no "
        f"supported version ({', '.join(PYTHON_MINORS)}) satisfies every "
        f"component" + (f"\n{details}" if details else "")
    )
    return None


def python_accepted(resolution: Resolution, version: str) -> bool:
    """Return whether every constraint in ``resolution`` accepts ``version``."""
    from packaging.specifiers import InvalidSpecifier

    try:
        if not python_specifier(resolution.target.python).contains(
            version, prereleases=True
        ):
            return False
        for resolved in resolution.components.values():
            declared = resolved.component.python
            if declared is not None and not python_specifier(declared).contains(
                version, prereleases=True
            ):
                return False
    except InvalidSpecifier:
        return False
    return True


def resolve(
    target: Target,
    catalog: Catalog,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> Resolution:
    """Place the target's components, compute closure, and report conflicts."""
    resolution = Resolution(target=target)
    display = target.relative_path(catalog.root)
    selections = dict(target.components)
    pending: list[str] = []
    for name in sorted(selections):
        if name not in catalog.components:
            resolution.errors.append(
                f"target {target.name!r} references unknown component {name!r}; "
                f"known components: {', '.join(sorted(catalog.components))}"
            )
            continue
        component = catalog.components[name]
        if not component.is_deps:
            pending.append(name)
            continue
        # A target selects a deps component to install its packages without
        # requiring a component: the flywheel runtime is core code, so the
        # environment that enables it opts in here.
        selection = selections[name]
        if selection.variant is not None:
            resolution.errors.append(
                f"target {target.name!r} selects deps component {name!r} with "
                "'variant'; deps components have no code and no optional groups"
            )
        if name not in resolution.deps:
            resolution.deps.append(name)
        resolution.components.setdefault(
            name,
            ResolvedComponent(component=component, variant=None),
        )
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
                f"{display}; expected one of "
                f"{', '.join(sorted(component.optional))}"
            )
        elif variant is not None and variant not in component.optional:
            resolution.errors.append(
                f"component {name!r} has no optional group {variant!r}; "
                f"expected one of {', '.join(sorted(component.optional)) or '<none>'}"
            )
            variant = None
        resolution.components[name] = ResolvedComponent(
            component=component,
            variant=variant,
        )
        for required in component.requires:
            if required not in catalog.components:
                resolution.errors.append(
                    f"component {name!r} requires unknown component {required!r}"
                )
                continue
            if catalog.components[required].is_deps:
                if required not in resolution.deps:
                    resolution.deps.append(required)
                # One deps component installs once, no matter how many
                # consumers require it. Keep the first resolved record so the
                # result does not depend on consumer order.
                resolution.components.setdefault(
                    required,
                    ResolvedComponent(
                        component=catalog.components[required],
                        variant=None,
                    ),
                )
                continue
            if required not in selections:
                selections[required] = Selection()
            pending.append(required)

    resolution.python = _choose_python(
        target, list(resolution.components.values()), resolution.errors, display
    )

    installed = sorted(resolution.main_installed())
    for index, left_name in enumerate(installed):
        for right_name in installed[index + 1 :]:
            left = resolution.components[left_name]
            right = resolution.components[right_name]
            if (
                right_name in left.component.env_conflicts
                or left_name in right.component.env_conflicts
            ):
                resolution.errors.append(
                    _format_conflict(left, right, target=target.name)
                )
    requirements = [
        (name, requirement)
        for name in installed
        for requirement in resolution.components[name].dependencies()
    ]
    requirements.extend((target.name, requirement) for requirement in core_dependencies)
    requirements.extend(
        (target.name, requirement) for requirement in target.dependencies
    )
    for package, pins in _pin_conflicts(requirements).items():
        lines = "\n".join(f"  {owner}: {package} {pin}" for owner, pin in pins)
        resolution.errors.append(
            f"target {target.name!r} has conflicting pins for {package!r}\n{lines}"
        )
    resolution.errors.extend(_override_conflicts(resolution))
    resolution.errors.extend(_target_duplicate_dependencies(resolution))
    resolution.errors = sorted(dict.fromkeys(resolution.errors))
    return resolution
