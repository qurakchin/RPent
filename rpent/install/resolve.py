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
    Target,
    python_specifier,
)

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

# ``packaging`` parses requirement strings and is imported where that happens,
# not at module import. ``tests.tooling.matrix`` imports this module through
# ``rpent.install`` and must run in a checkout that has no third-party packages
# installed; every install path still needs packaging.


@dataclass
class Resolution:
    """The components, environment settings, and diagnostics of one target."""

    target: Target
    #: Every component the target installs, keyed by name: the selections plus
    #: their ``requires`` closure.
    components: dict[str, Component] = field(default_factory=dict)
    #: Concrete Python minor every component accepts, newest supported first.
    python: str | None = None
    #: Host the environment is resolved for.
    platform: str = "linux-x86_64"
    #: Newest glibc baseline any component needs.
    manylinux: str = "2_31"
    index_url: str | None = None
    extra_index_urls: tuple[str, ...] = ()
    index_strategy: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether static checks passed."""
        return not self.errors


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
    they resolve together is uv's decision (``rpent-install check --resolve``).
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
    for name, component in sorted(resolution.components.items()):
        for package in _override_packages(component):
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
    for name, component in sorted(resolution.components.items()):
        owned = {
            identity[0]
            for identity in map(_canonical, component.dependencies)
            if identity is not None
        }
        for package in sorted(declared & owned):
            errors.append(
                f"target {target.name!r} lists {package!r} in its own "
                f"dependencies, but component {name!r} already requires it; "
                "keep the requirement where its owner declares it"
            )
    return errors


def _dependency_pins(component: Component) -> dict[str, str]:
    """Return package -> pin for one component's direct requirements."""
    identities = (_canonical(value) for value in component.dependencies)
    return {
        identity[0]: str(identity[1]) or identity[2]
        for identity in identities
        if identity is not None
    }


def _format_conflict(
    left: Component,
    right: Component,
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


def choose_python(components: list[Component], errors: list[str]) -> str | None:
    """Return the newest supported Python minor every component accepts.

    A component that declares no ``python`` accepts every supported minor, so a
    target whose components are all unconstrained resolves to the newest one.
    """
    from packaging.specifiers import InvalidSpecifier

    ranges: list[tuple[str, SpecifierSet]] = []
    for component in components:
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
        if all(
            supported.contains(minor, prereleases=True) for _, supported in ranges
        ):
            return minor
    details = "\n".join(
        f"  {name}: Python {supported}"
        for name, supported in sorted(ranges, key=lambda item: item[0])
    )
    errors.append(
        f"no supported Python version ({', '.join(PYTHON_MINORS)}) satisfies "
        "every component" + (f"\n{details}" if details else "")
    )
    return None


def python_accepted(resolution: Resolution, version: str) -> bool:
    """Return whether every component in ``resolution`` accepts ``version``."""
    from packaging.specifiers import InvalidSpecifier

    try:
        for component in resolution.components.values():
            declared = component.python
            if declared is not None and not python_specifier(declared).contains(
                version, prereleases=True
            ):
                return False
    except InvalidSpecifier:
        return False
    return True


def _baseline(value: str) -> tuple[int, int]:
    """Return a ``manylinux`` value as comparable numbers."""
    major, minor = value.split("_")
    return int(major), int(minor)


def _describe_settings(values: dict[str, list[str]]) -> str:
    """Return ``value (owners)`` pairs for an error message."""
    return "; ".join(
        f"{value!r} from {', '.join(owners)}"
        for value, owners in sorted(values.items())
    )


def _inherited(
    values: dict[str, list[str]],
    *,
    why: str,
    display: str,
    errors: list[str],
) -> str | None:
    """Return the value a component group declares when the target leaves it out.

    A component owns the index its packages come from, so a composition target
    that leaves ``index-url`` or ``index-strategy`` unset inherits it. A
    disagreement is an error: one environment cannot resolve against two
    indexes, and picking one side would silently break the other component.
    """
    if not values:
        return None
    if len(values) > 1:
        errors.append(
            f"{display}: components declare different {why}: "
            f"{_describe_settings(values)}; one environment resolves against "
            "one setting, so declare it on the target"
        )
        return None
    return next(iter(values))


def _apply_settings(
    resolution: Resolution, *, display: str
) -> None:
    """Fill the resolved index settings and glibc baseline."""
    target = resolution.target
    components = list(resolution.components.values())
    index_urls: dict[str, list[str]] = {}
    strategies: dict[str, list[str]] = {}
    extra_urls: dict[str, list[str]] = {}
    for component in components:
        if component.index_url:
            index_urls.setdefault(component.index_url, []).append(component.name)
        if component.index_strategy:
            strategies.setdefault(component.index_strategy, []).append(component.name)
        for url in component.extra_index_urls:
            extra_urls.setdefault(url, []).append(component.name)

    resolution.index_url = target.index_url or _inherited(
        index_urls,
        why="index URLs",
        display=display,
        errors=resolution.errors,
    )
    resolution.index_strategy = target.index_strategy or _inherited(
        strategies,
        why="index strategies",
        display=display,
        errors=resolution.errors,
    )
    resolution.extra_index_urls = tuple(
        sorted({*target.extra_index_urls, *extra_urls})
    )
    if components:
        resolution.manylinux = max(
            (component.manylinux for component in components), key=_baseline
        )


def _check_platform(
    resolution: Resolution, *, display: str
) -> None:
    """Report components that do not install on the resolved host."""
    for name, component in sorted(resolution.components.items()):
        if resolution.platform in component.platforms:
            continue
        resolution.errors.append(
            f"{display}: component {name!r} installs only on "
            f"{', '.join(component.platforms)}, not {resolution.platform}"
        )


def resolve(
    target: Target,
    catalog: Catalog,
    *,
    core_dependencies: tuple[str, ...] = (),
    platform: str = "linux-x86_64",
) -> Resolution:
    """Place the target's components, compute closure, and report conflicts."""
    resolution = Resolution(target=target, platform=platform)
    display = target.relative_path(catalog.root)
    pending = list(target.components)
    for name in target.components:
        if name not in catalog.components:
            resolution.errors.append(
                f"target {target.name!r} references unknown component {name!r}; "
                f"known components: {', '.join(sorted(catalog.components))}"
            )
    while pending:
        name = pending.pop(0)
        if name in resolution.components or name not in catalog.components:
            continue
        component = catalog.components[name]
        resolution.components[name] = component
        for required in component.requires:
            if required not in catalog.components:
                resolution.errors.append(
                    f"component {name!r} requires unknown component {required!r}"
                )
                continue
            pending.append(required)

    _apply_settings(resolution, display=display)
    _check_platform(resolution, display=display)
    resolution.python = choose_python(list(resolution.components.values()), resolution.errors)

    installed = sorted(resolution.components)
    for index, left_name in enumerate(installed):
        for right_name in installed[index + 1 :]:
            left = resolution.components[left_name]
            right = resolution.components[right_name]
            if (
                right_name in left.env_conflicts
                or left_name in right.env_conflicts
            ):
                resolution.errors.append(
                    _format_conflict(left, right, target=target.name)
                )
    requirements = [
        (name, requirement)
        for name in installed
        for requirement in resolution.components[name].dependencies
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
