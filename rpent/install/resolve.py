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

"""Resolve requested components into one environment and its errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from rpent.install.discovery import Catalog
from rpent.install.manifest import (
    PYTHON_MINORS,
    Component,
    environment_name,
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
    """The components, settings, and diagnostics of one environment."""

    #: Components the caller requested, in the order they were named.
    requested: tuple[str, ...] = ()
    #: Every component the environment installs, keyed by name: the requested
    #: components plus their ``requires`` closure.
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
    def name(self) -> str:
        """Return the environment name its requested components form."""
        return environment_name(self.requested)

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

    Marker-scoped lines select different constraints per platform, so the
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
            f"{package!r} in environment {resolution.name!r}; move the "
            "constraint into the component that needs it or merge the override "
            "files"
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
    return (
        f"{environment} places {left.name!r} and {right.name!r} "
        "in the same environment, but they conflict\n"
        + "\n".join(details)
        + f"\n  split {left.name} and {right.name} into separate environments "
        "and connect them by endpoint"
    )


def choose_python(components: list[Component], errors: list[str]) -> str | None:
    """Return the newest supported Python minor every component accepts.

    A component that declares no ``python`` accepts every supported minor, so
    an environment whose components are all unconstrained resolves to the
    newest one.
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
        if all(supported.contains(minor, prereleases=True) for _, supported in ranges):
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
    """Return the value the component group agrees on, if any.

    A component owns the index its packages come from, so the environment
    inherits the single value its closure declares. A disagreement is an error:
    one environment cannot resolve against two indexes, and picking one side
    would silently break the other component.
    """
    if not values:
        return None
    if len(values) > 1:
        errors.append(
            f"{display}: components declare different {why}: "
            f"{_describe_settings(values)}; one environment resolves against "
            "one setting, so install these components separately"
        )
        return None
    return next(iter(values))


def _apply_settings(resolution: Resolution, *, display: str) -> None:
    """Fill the resolved index settings and glibc baseline."""
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

    resolution.index_url = _inherited(
        index_urls,
        why="index URLs",
        display=display,
        errors=resolution.errors,
    )
    resolution.index_strategy = _inherited(
        strategies,
        why="index strategies",
        display=display,
        errors=resolution.errors,
    )
    resolution.extra_index_urls = tuple(sorted(extra_urls))
    if components:
        resolution.manylinux = max(
            (component.manylinux for component in components), key=_baseline
        )


def resolve(
    requested: Iterable[str],
    catalog: Catalog,
    *,
    core_dependencies: tuple[str, ...] = (),
    platform: str = "linux-x86_64",
) -> Resolution:
    """Place the requested components, compute closure, and report conflicts."""
    selected = tuple(dict.fromkeys(requested))
    resolution = Resolution(requested=selected, platform=platform)
    display = f"environment {resolution.name!r}"
    pending = list(selected)
    for name in selected:
        if name not in catalog.components:
            resolution.errors.append(
                f"{display} references unknown component {name!r}; "
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
    resolution.python = choose_python(
        list(resolution.components.values()), resolution.errors
    )

    installed = sorted(resolution.components)
    for index, left_name in enumerate(installed):
        for right_name in installed[index + 1 :]:
            left = resolution.components[left_name]
            right = resolution.components[right_name]
            if right_name in left.env_conflicts or left_name in right.env_conflicts:
                resolution.errors.append(
                    _format_conflict(left, right, environment=display)
                )
    requirements = [
        (name, requirement)
        for name in installed
        for requirement in resolution.components[name].dependencies
    ]
    requirements.extend(("core", requirement) for requirement in core_dependencies)
    for package, pins in _pin_conflicts(requirements).items():
        lines = "\n".join(f"  {owner}: {package} {pin}" for owner, pin in pins)
        resolution.errors.append(
            f"{display} has conflicting pins for {package!r}\n{lines}"
        )
    resolution.errors.extend(_override_conflicts(resolution))
    resolution.errors = sorted(dict.fromkeys(resolution.errors))
    return resolution
