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

"""Typed component manifests (``component.toml``) and profiles (``envs/*.toml``).

Manifests own dependency declarations. Profiles only choose components, their
placement, and an optional variant; they never repeat a component's packages.
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
KINDS = ("robot", "toolkit", "capability")
PLACEMENTS = ("in-env", "external-env", "remote")
_PYTHON_MINOR = re.compile(r"^\d+\.\d+$")
_MANYLINUX = re.compile(r"^\d+_\d+$")


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
        groups[name] = tuple(values)
    return groups


@dataclass(frozen=True)
class Component:
    """One install boundary declared by ``component.toml``."""

    name: str
    kind: str
    path: Path
    probe: str
    python: str | None
    platforms: tuple[str, ...]
    requires: tuple[str, ...]
    env_conflicts: tuple[str, ...]
    placements: tuple[str, ...]
    default_placement: str
    dependencies: tuple[str, ...]
    optional: dict[str, tuple[str, ...]]
    overrides: tuple[Path, ...]
    docs: str | None
    manifest_sha256: str

    @property
    def manifest_path(self) -> Path:
        """Return the manifest path."""
        return self.path / "component.toml"

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
    env: str | None = None


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
    lock: str | None
    core: bool
    generate_extra: bool
    extra: str | None
    description: str | None
    manylinux: str = "2_31"

    def relative_lock(self) -> Path | None:
        """Return the declared lock path relative to the repository root."""
        return Path(self.lock) if self.lock else None


def load_component(path: Path) -> Component:
    """Load and validate one ``component.toml``."""
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    if path.parent.name != name:
        raise InstallConfigError(
            f"{path}: name {name!r} must match its directory {path.parent.name!r}"
        )
    kind = data.get("kind")
    if kind not in KINDS:
        raise InstallConfigError(f"{path}: 'kind' must be one of {', '.join(KINDS)}")
    probe = data.get("probe")
    if not isinstance(probe, str) or not probe:
        raise InstallConfigError(f"{path}: 'probe' must be a non-empty import path")
    python = _optional_string(data, "python", path)
    platforms = _string_list(data, "platforms", path)
    placements = _placement_list(data, path)
    default_placement = data.get("default_placement", placements[0])
    if default_placement not in placements:
        raise InstallConfigError(
            f"{path}: 'default_placement' must be one of {', '.join(placements)}"
        )
    optional = _optional_groups(data, path)
    default_variant = data.get("variant")
    if default_variant is not None and default_variant not in optional:
        raise InstallConfigError(
            f"{path}: 'variant' {default_variant!r} is not an optional group"
        )
    overrides = tuple(
        path.parent / relative for relative in _string_list(data, "overrides", path)
    )
    for override in overrides:
        if not override.is_file():
            raise InstallConfigError(f"{path}: override file not found: {override}")
    return Component(
        name=name,
        kind=kind,
        path=path.parent,
        probe=probe,
        python=python,
        platforms=platforms,
        requires=_string_list(data, "requires", path),
        env_conflicts=_string_list(data, "env_conflicts", path),
        placements=placements,
        default_placement=default_placement,
        dependencies=_string_list(data, "dependencies", path),
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
        unknown = sorted(set(raw) - {"placement", "variant", "env"})
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
        env = raw.get("env")
        if env is not None and (not isinstance(env, str) or not env):
            raise InstallConfigError(
                f"{path}: components.{component_name}.env must be a string"
            )
        if placement == "in-env" and env is not None:
            raise InstallConfigError(
                f"{path}: components.{component_name} places an in-env component "
                "inside a named external environment; remove 'env'"
            )
        if placement == "external-env" and env is None:
            raise InstallConfigError(
                f"{path}: components.{component_name} uses external-env "
                "without an 'env' name"
            )
        components[component_name] = Selection(
            placement=placement, variant=variant, env=env
        )
    extra_value = data.get("extra", name)
    if extra_value is False:
        generate_extra = False
        extra = None
    elif extra_value is True or isinstance(extra_value, str):
        generate_extra = True
        extra = name if extra_value is True else extra_value
        if not extra:
            raise InstallConfigError(f"{path}: 'extra' must be a non-empty string")
    else:
        raise InstallConfigError(f"{path}: 'extra' must be a string or false")
    core = data.get("core", True)
    if not isinstance(core, bool):
        raise InstallConfigError(f"{path}: 'core' must be a boolean")
    manylinux = data.get("manylinux", "2_31")
    if not isinstance(manylinux, str) or not _MANYLINUX.match(manylinux):
        raise InstallConfigError(
            f"{path}: 'manylinux' must name a glibc baseline such as '2_31'"
        )
    index_url = _optional_string(data, "index-url", path)
    return Profile(
        name=name,
        path=path,
        python=python,
        platform=platform,
        components=components,
        dependencies=_string_list(data, "dependencies", path),
        index_url=index_url,
        extra_index_urls=_string_list(data, "extra-index-urls", path),
        lock=_optional_string(data, "lock", path),
        core=core,
        generate_extra=generate_extra,
        extra=extra,
        description=_optional_string(data, "description", path),
        manylinux=manylinux,
    )
