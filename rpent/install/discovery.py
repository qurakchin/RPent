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

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    Component,
    Target,
    load_component,
    load_deps_component,
    load_target,
    target_from_component,
)

#: Every component root and the glob that finds it. Directory kinds read a
#: ``component.toml``; the ``deps`` kind reads one file per component.
COMPONENT_ROOTS = (
    ("robots/*/component.toml", "robot"),
    ("components/models/*/component.toml", "model"),
    ("components/toolkits/*/component.toml", "toolkit"),
    ("installs/deps/*.toml", "deps"),
)


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
        InstallConfigError: a manifest is invalid, duplicated, or has a kind
            that does not match the directory root it lives under.
    """
    repo_root = (root or repository_root()).resolve()
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
    """Allow ``imports`` on robot slices, naming a co-installed robot.

    Toolkits and model services share a contract instead of importing each
    other's modules, so an ``imports`` entry on either is a manifest error
    rather than a boundary the layout check has to honour.
    """
    reverse = {
        other.name: set(other.requires)
        for other in components.values()
        if not other.is_deps
    }
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


def _baseline(value: str) -> tuple[int, int]:
    """Return a ``manylinux`` value as comparable numbers."""
    major, minor = value.split("_")
    return int(major), int(minor)


def _installed_components(
    target: Target, components: dict[str, Component]
) -> list[Component]:
    """Return the closure components this target installs into its environment.

    Remotely placed components install nothing here, so their index and
    platform requirements do not constrain this environment.
    """
    seen: set[str] = set()
    pending = list(target.components)
    installed: list[Component] = []
    while pending:
        name = pending.pop(0)
        if name in seen or name not in components:
            continue
        seen.add(name)
        component = components[name]
        selection = target.components.get(name)
        # A deps component always installs with its consumers.
        placement = (
            "in-env"
            if component.is_deps
            else (
                selection.placement
                if selection is not None and selection.placement is not None
                else component.default_placement
            )
        )
        if placement != "remote":
            installed.append(component)
        pending.extend(component.requires)
    return installed


def _inherit_settings(
    target: Target,
    components: dict[str, Component],
    root: Path,
) -> Target:
    """Apply the index settings the target's components declare.

    A component owns the index its packages come from, so a composition target
    that leaves ``index-url`` or ``index-strategy`` unset inherits them, and
    extra index URLs are unioned with the target's. A disagreement is an error:
    the environment cannot resolve against two indexes at once, and picking one
    side would silently break the other component.
    """
    installed = _installed_components(target, components)
    if not installed:
        return target

    index_urls: dict[str, list[str]] = {}
    strategies: dict[str, list[str]] = {}
    extra_urls: dict[str, list[str]] = {}
    for component in installed:
        settings = component.settings
        if settings.index_url:
            index_urls.setdefault(settings.index_url, []).append(component.name)
        if settings.index_strategy:
            strategies.setdefault(settings.index_strategy, []).append(component.name)
        for url in settings.extra_index_urls:
            extra_urls.setdefault(url, []).append(component.name)

    index_url = target.index_url
    if index_url is None and index_urls:
        if len(index_urls) > 1:
            raise InstallConfigError(
                f"{target.relative_path(root)}: components declare different "
                f"index URLs: {_describe_settings(index_urls)}; one environment "
                "resolves against one index"
            )
        index_url = next(iter(index_urls))

    index_strategy = target.index_strategy
    if index_strategy is None and strategies:
        if len(strategies) > 1:
            raise InstallConfigError(
                f"{target.relative_path(root)}: components declare different "
                f"index strategies: {_describe_settings(strategies)}; set "
                "'index-strategy' on the target to decide"
            )
        index_strategy = next(iter(strategies))

    declared = max(
        (component.settings.manylinux for component in installed), key=_baseline
    )
    if _baseline(declared) > _baseline(target.manylinux):
        requiring = ", ".join(
            component.name
            for component in installed
            if component.settings.manylinux == declared
        )
        raise InstallConfigError(
            f"{target.relative_path(root)}: manylinux {target.manylinux} cannot serve "
            f"{requiring}, which needs manylinux {declared}; raise 'manylinux' "
            "on the target"
        )

    extra_index_urls = tuple(sorted({*target.extra_index_urls, *extra_urls}))
    if (
        index_url == target.index_url
        and index_strategy == target.index_strategy
        and extra_index_urls == target.extra_index_urls
    ):
        return target
    return replace(
        target,
        index_url=index_url,
        index_strategy=index_strategy,
        extra_index_urls=extra_index_urls,
    )


def _describe_settings(values: dict[str, list[str]]) -> str:
    """Return ``value (owners)`` pairs for an error message."""
    return "; ".join(
        f"{value!r} from {', '.join(owners)}"
        for value, owners in sorted(values.items())
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
            target = _inherit_settings(load_target(path), components, repo_root)
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
        if component.is_deps or component.variant_required or component.kind == "robot":
            # A deps component has no code, a variant component cannot choose
            # its variant by name, and a robot is an integration, not an
            # install unit: each needs a target file that names what to
            # install.
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
    selected = target.components.get(component.name)
    if selected is None:
        raise InstallConfigError(
            f"target {target.name!r} in {target.relative_path(repo_root)} "
            f"overrides robot component {component.manifest_path} but does "
            f"not select it; add [components.{component.name}] to the target "
            "or rename it"
        )


def discover_targets(root: Path | None = None) -> dict[str, Target]:
    """Load every target, including one synthesized per non-robot component.

    A target that reuses a component name without being a robot's override,
    an override that does not install its own robot, and a composition target
    whose installed components disagree about an index or need a newer
    ``manylinux`` baseline are rejected rather than installed under a silently
    narrowed environment.
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
