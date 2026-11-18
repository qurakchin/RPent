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

"""Resolve component names into one environment's contents and diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpent.install.discovery import Catalog
from rpent.install.manifest import Component

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

# ``packaging`` parses requirement strings and is imported where that happens,
# not at module import. The repository tooling (``tests.tooling.matrix``)
# imports manifest discovery through ``rpent.install`` and must run in a
# checkout that has no third-party packages installed; every install path still
# needs packaging.


@dataclass
class Resolution:
    """The components one environment contains, and why it cannot be built."""

    #: The component names the caller asked for, sorted and deduplicated.
    targets: tuple[str, ...]
    #: Every component in the environment, including the ``requires`` closure.
    components: dict[str, Component] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    #: Index settings merged from the components; parts of the closure that
    #: disagree are errors.
    index_url: str | None = None
    extra_index_urls: tuple[str, ...] = ()
    index_strategy: str | None = None

    @property
    def ok(self) -> bool:
        """Return whether static checks passed."""
        return not self.errors

    def dependencies(self) -> tuple[str, ...]:
        """Return every direct dependency in the environment, deduplicated."""
        requirements = [
            requirement
            for component in self.components.values()
            for requirement in component.dependencies
        ]
        return tuple(dict.fromkeys(requirements))


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


def _dependency_pins(component: Component) -> dict[str, str]:
    """Return package -> pin for one component's direct requirements."""
    identities = (_canonical(value) for value in component.dependencies)
    return {
        identity[0]: str(identity[1]) or identity[2]
        for identity in identities
        if identity is not None
    }


def _format_conflict(left: Component, right: Component) -> str:
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
        f"components {left.name!r} and {right.name!r} cannot share an "
        "environment\n"
        + "\n".join(details)
        + "\ninstall each target in its own environment: "
        f"`rpent-install install {left.name}` and "
        f"`rpent-install install {right.name}`"
    )


def _override_packages(component: Component) -> set[str]:
    """Return the packages one component's override files constrain.

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


def _override_conflicts(components: dict[str, Component]) -> list[str]:
    """Return errors for packages two components override at once.

    uv merges every component's override into one resolution, so two files
    constraining the same package leave the winner to file order. Report the
    pair and let the components own their constraints or share one file.
    """
    owners: dict[str, list[str]] = {}
    for name, component in sorted(components.items()):
        for package in _override_packages(component):
            owners.setdefault(package, []).append(name)
    errors: list[str] = []
    for package, names in sorted(owners.items()):
        if len(names) < 2:
            continue
        errors.append(
            f"components {', '.join(repr(name) for name in names)} both override "
            f"{package!r} in one environment; move the constraint into the "
            "component that needs it or merge the override files"
        )
    return errors


def python_errors(
    version: str,
    components: Iterable[Component],
    *,
    owner: str = "this environment",
) -> list[str]:
    """Return errors for components that do not support Python ``version``."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    try:
        parsed = Version(version)
    except InvalidVersion:
        return []
    errors: list[str] = []
    for component in sorted(components, key=lambda item: item.name):
        if component.python is None:
            continue
        try:
            supported = SpecifierSet(component.python)
        except InvalidSpecifier as exc:
            errors.append(
                f"{component.manifest_path}: invalid python range "
                f"{component.python!r}: {exc}"
            )
            continue
        if not supported.contains(parsed, prereleases=True):
            errors.append(
                f"component {component.name!r} requires Python "
                f"{component.python}, but {owner} uses {version}"
            )
    return errors


def platform_errors(platform: str, components: Iterable[Component]) -> list[str]:
    """Return errors for components that do not support ``platform``."""
    return [
        f"component {component.name!r} supports "
        f"{', '.join(component.platforms)}, but this environment runs on "
        f"{platform}"
        for component in sorted(components, key=lambda item: item.name)
        if component.platforms and platform not in component.platforms
    ]


def _merge_index_settings(
    resolution: Resolution, components: Iterable[Component]
) -> None:
    """Merge index settings, reporting components that disagree."""
    extra: list[str] = []
    for component in sorted(components, key=lambda item: item.name):
        if component.index_url is not None:
            if resolution.index_url not in (None, component.index_url):
                resolution.errors.append(
                    f"component {component.name!r} selects index "
                    f"{component.index_url!r}, but another component in this "
                    f"environment selects {resolution.index_url!r}; install them "
                    "in separate environments"
                )
            resolution.index_url = component.index_url
        if component.index_strategy is not None:
            if resolution.index_strategy not in (None, component.index_strategy):
                resolution.errors.append(
                    f"component {component.name!r} selects index strategy "
                    f"{component.index_strategy!r}, but another component in this "
                    f"environment selects {resolution.index_strategy!r}; install "
                    "them in separate environments"
                )
            resolution.index_strategy = component.index_strategy
        extra.extend(component.extra_index_urls)
    resolution.extra_index_urls = tuple(dict.fromkeys(extra))


def resolve(
    targets: Iterable[str],
    catalog: Catalog,
    *,
    core_dependencies: tuple[str, ...] = (),
    python: str | None = None,
    platform: str | None = None,
) -> Resolution:
    """Return the environment a ``install <targets>`` command would create.

    ``python`` and ``platform`` describe the environment that will run the
    components; ``rpent-install check`` leaves them out to validate manifests
    without tying the answer to the machine that runs the check.
    """
    names = tuple(sorted(set(targets)))
    resolution = Resolution(targets=names)
    if not names:
        resolution.errors.append("name at least one component to install")
        return resolution
    pending = list(names)
    for name in names:
        if name not in catalog.components:
            resolution.errors.append(
                f"unknown component {name!r}; known components: "
                f"{', '.join(sorted(catalog.components))}"
            )
    while pending:
        name = pending.pop(0)
        if name in resolution.components:
            continue
        component = catalog.components.get(name)
        if component is None:
            # Reported above or by the requires check that queued it.
            continue
        resolution.components[name] = component
        pending.extend(component.requires)

    ordered = dict(sorted(resolution.components.items()))
    resolution.components = ordered

    for component in ordered.values():
        for required in component.requires:
            if required in component.env_conflicts or (
                required in ordered
                and component.name in ordered[required].env_conflicts
            ):
                resolution.errors.append(
                    f"component {component.name!r} requires {required!r} but "
                    "the two declare env_conflicts; fix their manifests"
                )

    if python is not None:
        resolution.errors.extend(
            python_errors(python, ordered.values(), owner="the environment")
        )
    if platform is not None:
        resolution.errors.extend(platform_errors(platform, ordered.values()))
    _merge_index_settings(resolution, ordered.values())

    names_in_env = list(ordered)
    for index, left_name in enumerate(names_in_env):
        for right_name in names_in_env[index + 1 :]:
            left = ordered[left_name]
            right = ordered[right_name]
            if right_name in left.env_conflicts or left_name in right.env_conflicts:
                resolution.errors.append(_format_conflict(left, right))

    requirements = [
        (component.name, requirement)
        for component in ordered.values()
        for requirement in component.dependencies
    ]
    if core_dependencies:
        requirements.extend(("rpent", requirement) for requirement in core_dependencies)
    for package, pins in _pin_conflicts(requirements).items():
        lines = "\n".join(f"  {owner}: {package} {pin}" for owner, pin in pins)
        resolution.errors.append(f"conflicting pins for {package!r}\n{lines}")
    resolution.errors.extend(_override_conflicts(ordered))
    resolution.errors = sorted(dict.fromkeys(resolution.errors))
    return resolution
