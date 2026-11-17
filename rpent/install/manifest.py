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

"""Typed component manifests (``component.toml``) and profiles.

Profiles live at ``installs/profiles/<name>.toml``.

Manifests own a component's packages. Profiles choose components, their
placement, and an optional variant; they may add packages that belong to no
component (the test and lint tools in ``dev``) but never repeat a component's
declarations.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpent.install.errors import InstallConfigError

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

SCHEMA = 1
KINDS = ("robot", "model", "deps")
#: Kinds declared by ``component.toml`` inside the component's own directory.
DIRECTORY_KINDS = ("robot", "model")
PLACEMENTS = ("in-env", "external-env", "remote")
#: ``uv``'s multi-index strategies; see ``--index-strategy`` in ``uv pip compile``.
INDEX_STRATEGIES = ("first-index", "unsafe-first-match", "unsafe-best-match")
_PYTHON_MINOR = re.compile(r"^\d+\.\d+$")
_MANYLINUX = re.compile(r"^\d+_\d+$")
#: A git dependency must name an immutable ref. Branches move, which makes a
#: dependency declaration install different code tomorrow.
_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_VERSION_TAG = re.compile(r"^v?\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?$")


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except OSError as exc:
        raise InstallConfigError(f"{path}: cannot read file: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise InstallConfigError(f"{path}: invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InstallConfigError(f"{path}: is not valid UTF-8: {exc}") from exc


def _schema(data: dict[str, Any], path: Path) -> None:
    schema = data.get("schema")
    if schema != SCHEMA:
        raise InstallConfigError(
            f"{path}: unsupported schema {schema!r}; expected {SCHEMA}"
        )


def _name(data: dict[str, Any], path: Path) -> str:
    value = data.get("name")
    if not isinstance(value, str) or not value:
        raise InstallConfigError(f"{path}: 'name' must be a non-empty string")
    return value


def _optional_string(data: dict[str, Any], key: str, path: Path) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise InstallConfigError(f"{path}: '{key}' must be a non-empty string")
    return value


def _string_list(
    data: dict[str, Any], key: str, path: Path, *, required: bool = False
) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        if required:
            raise InstallConfigError(f"{path}: missing required field '{key}'")
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise InstallConfigError(f"{path}: '{key}' must be a list of strings")
    return tuple(value)


def _git_ref(requirement: str) -> str | None:
    """Return the ref of a ``name @ git+...@ref`` requirement, if any."""
    marker = requirement.find("git+")
    if marker < 0:
        return None
    target = requirement[marker + len("git+") :].strip()
    _, separator, ref = target.rpartition("@")
    if not separator:
        return None
    return ref.split("#", 1)[0] or None


def _check_git_dependency(requirement: str, path: Path) -> None:
    """Reject a mutable git ref; commits and version tags are reproducible."""
    if "git+" not in requirement:
        return
    ref = _git_ref(requirement)
    if ref is None:
        raise InstallConfigError(
            f"{path}: dependency {requirement!r} has no git ref; pin a "
            "40-character commit or a version tag"
        )
    if _FULL_COMMIT.fullmatch(ref) or _VERSION_TAG.fullmatch(ref):
        return
    raise InstallConfigError(
        f"{path}: dependency {requirement!r} pins git ref {ref!r}; use a "
        "40-character commit or a version tag so the dependency cannot change when "
        "the branch moves"
    )


def _dependency_list(
    data: dict[str, Any], key: str, path: Path, *, required: bool = False
) -> tuple[str, ...]:
    """Read a dependency list and validate its direct git references."""
    values = _string_list(data, key, path, required=required)
    for value in values:
        _check_git_dependency(value, path)
    return values


def _placement_list(data: dict[str, Any], path: Path) -> tuple[str, ...]:
    placements = _string_list(data, "placement", path) or ("in-env",)
    unknown = sorted(set(placements) - set(PLACEMENTS))
    if unknown:
        raise InstallConfigError(
            f"{path}: unknown placement(s) {', '.join(unknown)}; "
            f"expected one of {', '.join(PLACEMENTS)}"
        )
    return placements


def _optional_groups(data: dict[str, Any], path: Path) -> dict[str, tuple[str, ...]]:
    optional = data.get("optional", {})
    if not isinstance(optional, dict):
        raise InstallConfigError(f"{path}: 'optional' must be a table")
    groups: dict[str, tuple[str, ...]] = {}
    for name, values in optional.items():
        if not isinstance(name, str) or not name:
            raise InstallConfigError(f"{path}: optional group names must be strings")
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise InstallConfigError(
                f"{path}: optional group {name!r} must be a list of strings"
            )
        for value in values:
            _check_git_dependency(value, path)
        groups[name] = tuple(values)
    return groups


@dataclass(frozen=True)
class Component:
    """One install boundary declared by ``component.toml``."""

    name: str
    kind: str
    path: Path
    manifest: Path
    probe: str
    python: str | None
    platforms: tuple[str, ...]
    requires: tuple[str, ...]
    imports: tuple[str, ...]
    env_conflicts: tuple[str, ...]
    placements: tuple[str, ...]
    default_placement: str | None
    default_variant: str | None
    variant_required: bool
    dependencies: tuple[str, ...]
    optional: dict[str, tuple[str, ...]]
    overrides: tuple[Path, ...]
    docs: str | None
    manifest_sha256: str

    @property
    def manifest_path(self) -> Path:
        """Return the manifest path."""
        return self.manifest

    @property
    def is_deps(self) -> bool:
        """Return whether this component only groups packages for its consumers."""
        return self.kind == "deps"

    def dependencies_for(self, variant: str | None) -> tuple[str, ...]:
        """Return the component's direct dependencies for one optional variant."""
        if variant is None:
            return self.dependencies
        if variant not in self.optional:
            raise InstallConfigError(
                f"{self.manifest_path}: unknown variant {variant!r}; "
                f"expected one of {', '.join(sorted(self.optional)) or '<none>'}"
            )
        return self.dependencies + self.optional[variant]


@dataclass(frozen=True)
class Selection:
    """How a profile places one component."""

    placement: str | None = None
    variant: str | None = None
    profile: str | None = None


@dataclass(frozen=True)
class Profile:
    """One supported environment composed from components."""

    name: str
    path: Path
    python: str
    platform: str
    components: dict[str, Selection]
    dependencies: tuple[str, ...]
    index_url: str | None
    extra_index_urls: tuple[str, ...]
    index_strategy: str | None
    core: bool
    description: str | None
    manylinux: str = "2_31"
    #: A development diagnostic built for one component rather than a profile
    #: declared in ``installs/profiles/``; nothing may present it as one.
    synthetic: bool = False


def load_component(path: Path) -> Component:
    """Load and validate one ``component.toml`` from a component directory."""
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    if path.parent.name != name:
        raise InstallConfigError(
            f"{path}: name {name!r} must match its directory {path.parent.name!r}"
        )
    kind = data.get("kind")
    if kind == "deps":
        raise InstallConfigError(
            f"{path}: 'deps' components live at installs/deps/<name>.toml"
        )
    return _component(data, path, name=name, kind=kind)


def load_deps_component(path: Path) -> Component:
    """Load and validate one ``installs/deps/<name>.toml`` manifest."""
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    if path.stem != name:
        raise InstallConfigError(
            f"{path}: name {name!r} must match its file name {path.stem!r}"
        )
    kind = data.get("kind")
    if kind != "deps":
        raise InstallConfigError(
            f"{path}: 'kind' must be 'deps'; use component.toml in a component "
            "directory for robots and models"
        )
    if "placement" in data or "default_placement" in data:
        raise InstallConfigError(
            f"{path}: deps components follow the components that require them; "
            "remove 'placement' and 'default_placement'"
        )
    if data.get("imports"):
        raise InstallConfigError(
            f"{path}: deps components have no code; remove 'imports'"
        )
    if data.get("requires"):
        # Deps components have no code to call anything, and the resolver only
        # walks `requires` from the components that consumers place. Accepting
        # the field would silently ignore it.
        raise InstallConfigError(
            f"{path}: deps components have no code and cannot require other "
            "components; list their packages under 'dependencies'"
        )
    return _component(data, path, name=name, kind=kind)


def _component(
    data: dict[str, Any],
    path: Path,
    *,
    name: str,
    kind: Any,
) -> Component:
    """Build a component from parsed data, validating shared fields."""
    if kind not in KINDS:
        raise InstallConfigError(f"{path}: 'kind' must be one of {', '.join(KINDS)}")
    probe = data.get("probe")
    if not isinstance(probe, str) or not probe:
        raise InstallConfigError(f"{path}: 'probe' must be a non-empty import path")
    python = _optional_string(data, "python", path)
    platforms = _string_list(data, "platforms", path)
    if kind == "deps":
        placements: tuple[str, ...] = ()
        default_placement: str | None = None
    else:
        placements = _placement_list(data, path)
        default_placement = data.get("default_placement", placements[0])
        if default_placement not in placements:
            raise InstallConfigError(
                f"{path}: 'default_placement' must be one of {', '.join(placements)}"
            )
    optional = _optional_groups(data, path)
    default_variant = _optional_string(data, "variant", path)
    if default_variant is not None and default_variant not in optional:
        raise InstallConfigError(
            f"{path}: 'variant' {default_variant!r} is not an optional group"
        )
    variant_required = data.get("variant_required", False)
    if not isinstance(variant_required, bool):
        raise InstallConfigError(f"{path}: 'variant_required' must be a boolean")
    if variant_required and not optional:
        raise InstallConfigError(
            f"{path}: 'variant_required' is set but there are no [optional] groups"
        )
    if variant_required and default_variant is not None:
        raise InstallConfigError(
            f"{path}: 'variant_required' cannot be combined with a default 'variant'"
        )
    declared_overrides = _string_list(data, "overrides", path)
    for relative in declared_overrides:
        if Path(relative).is_absolute():
            raise InstallConfigError(
                f"{path}: override {relative!r} must be relative to the component "
                "directory, so the checkout can move"
            )
    overrides = tuple(path.parent / relative for relative in declared_overrides)
    for override in overrides:
        if not override.is_file():
            raise InstallConfigError(f"{path}: override file not found: {override}")
    return Component(
        name=name,
        kind=kind,
        path=path.parent,
        manifest=path,
        probe=probe,
        python=python,
        platforms=platforms,
        requires=_string_list(data, "requires", path),
        imports=_string_list(data, "imports", path),
        env_conflicts=_string_list(data, "env_conflicts", path),
        placements=placements,
        default_placement=default_placement,
        default_variant=default_variant,
        variant_required=variant_required,
        dependencies=_dependency_list(data, "dependencies", path),
        optional=optional,
        overrides=overrides,
        docs=_optional_string(data, "docs", path),
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def load_profile(path: Path) -> Profile:
    """Load and validate one environment profile."""
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    if path.stem != name:
        raise InstallConfigError(
            f"{path}: name {name!r} must match its file name {path.stem!r}"
        )
    python = data.get("python")
    if not isinstance(python, str) or not _PYTHON_MINOR.match(python):
        raise InstallConfigError(
            f"{path}: 'python' must pin a minor version such as '3.11'"
        )
    platform = data.get("platform")
    if not isinstance(platform, str) or not platform:
        raise InstallConfigError(f"{path}: 'platform' must be a non-empty string")
    raw_components = data.get("components", {})
    if not isinstance(raw_components, dict):
        raise InstallConfigError(f"{path}: 'components' must be a table")
    components: dict[str, Selection] = {}
    for component_name, raw in raw_components.items():
        if not isinstance(raw, dict):
            raise InstallConfigError(
                f"{path}: components.{component_name} must be a table"
            )
        unknown = sorted(set(raw) - {"placement", "variant", "profile"})
        if unknown:
            raise InstallConfigError(
                f"{path}: components.{component_name} has unknown field(s): "
                f"{', '.join(unknown)}"
            )
        placement = raw.get("placement")
        if placement is not None and placement not in PLACEMENTS:
            raise InstallConfigError(
                f"{path}: components.{component_name}.placement must be one of "
                f"{', '.join(PLACEMENTS)}"
            )
        variant = raw.get("variant")
        if variant is not None and not isinstance(variant, str):
            raise InstallConfigError(
                f"{path}: components.{component_name}.variant must be a string"
            )
        external_profile = raw.get("profile")
        if external_profile is not None and (
            not isinstance(external_profile, str) or not external_profile
        ):
            raise InstallConfigError(
                f"{path}: components.{component_name}.profile must be a string"
            )
        if placement == "in-env" and external_profile is not None:
            raise InstallConfigError(
                f"{path}: components.{component_name} places an in-env component "
                "inside a named external environment; remove 'profile'"
            )
        if placement == "external-env" and external_profile is None:
            raise InstallConfigError(
                f"{path}: components.{component_name} uses external-env "
                "without a 'profile' name"
            )
        components[component_name] = Selection(
            placement=placement, variant=variant, profile=external_profile
        )
    core = data.get("core", True)
    if not isinstance(core, bool):
        raise InstallConfigError(f"{path}: 'core' must be a boolean")
    manylinux = data.get("manylinux", "2_31")
    if not isinstance(manylinux, str) or not _MANYLINUX.match(manylinux):
        raise InstallConfigError(
            f"{path}: 'manylinux' must name a glibc baseline such as '2_31'"
        )
    index_url = _optional_string(data, "index-url", path)
    index_strategy = _optional_string(data, "index-strategy", path)
    if index_strategy is not None and index_strategy not in INDEX_STRATEGIES:
        raise InstallConfigError(
            f"{path}: 'index-strategy' must be one of {', '.join(INDEX_STRATEGIES)}"
        )
    return Profile(
        name=name,
        path=path,
        python=python,
        platform=platform,
        components=components,
        dependencies=_dependency_list(data, "dependencies", path),
        index_url=index_url,
        extra_index_urls=_string_list(data, "extra-index-urls", path),
        index_strategy=index_strategy,
        core=core,
        description=_optional_string(data, "description", path),
        manylinux=manylinux,
    )
