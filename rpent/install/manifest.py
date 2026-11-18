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

"""Install manifests: code components and the targets users install.

One schema covers both. A directory component (``robots/``,
``components/models/``, ``components/toolkits/``) declares the packages it owns
and can be installed directly by name. A target is a manifest without code:
``installs/targets/<name>.toml`` composes components, ``tests/targets/`` serves
only tests and CI. Targets may add packages that belong to no component but
never repeat a component's declarations.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rpent.install.errors import InstallConfigError

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

SCHEMA = 2
KINDS = ("robot", "toolkit", "model", "deps", "target")
#: Kinds declared by ``component.toml`` inside the component's own directory.
DIRECTORY_KINDS = ("robot", "toolkit", "model")
#: How a target may place a component. ``remote`` means the target installs
#: only the client and the contract; the service runs outside this repository.
#: A service that needs its own environment is a separate target, never a
#: second environment owned by this one.
PLACEMENTS = ("in-env", "remote")
#: ``uv``'s multi-index strategies; see ``--index-strategy`` in ``uv pip compile``.
INDEX_STRATEGIES = ("first-index", "unsafe-first-match", "unsafe-best-match")
#: Python minors the repository supports, newest first. A requested range is
#: resolved to the highest minor in this list that all components accept.
PYTHON_MINORS = ("3.12", "3.11", "3.10")
_MANYLINUX = re.compile(r"^\d+_\d+$")
#: A git dependency must name an immutable ref. Branches move, which makes a
#: lock compiled yesterday install different code tomorrow.
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


#: Top-level keys each manifest kind may declare. A key outside the set is a
#: typo or a leftover from an earlier field name; ignoring it would leave the
#: manifest saying something the installer never reads.
_ALLOWED_KEYS = {
    "component": frozenset(
        {
            "schema",
            "name",
            "kind",
            "probe",
            "python",
            "placement",
            "variant",
            "variant_required",
            "requires",
            "imports",
            "env_conflicts",
            "dependencies",
            "optional",
            "overrides",
            "docs",
            "extra",
            "core",
            "description",
            "index-url",
            "extra-index-urls",
            "index-strategy",
            "manylinux",
            "lock",
        }
    ),
    "target": frozenset(
        {
            "schema",
            "name",
            "kind",
            "python",
            "components",
            "dependencies",
            "extra",
            "core",
            "description",
            "index-url",
            "extra-index-urls",
            "index-strategy",
            "manylinux",
            "lock",
        }
    ),
}


def _reject_unknown(data: dict[str, Any], path: Path, kind: str) -> None:
    """Reject top-level fields the manifest kind does not define."""
    unknown = sorted(set(data) - _ALLOWED_KEYS[kind])
    if unknown:
        raise InstallConfigError(
            f"{path}: unknown {kind} field(s): {', '.join(unknown)}; "
            f"expected one of {', '.join(sorted(_ALLOWED_KEYS[kind]))}"
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
        "40-character commit or a version tag so the lock cannot change when "
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


def python_specifier(value: str) -> "SpecifierSet":
    """Return the PEP 440 specification a Python request denotes.

    A bare version such as ``3.11`` means ``==3.11.*``: targets and components
    mean the minor, not one patch release. A range is used as written.
    """
    from packaging.specifiers import SpecifierSet

    text = value.strip()
    if text[:1].isdigit():
        text = f"=={text}.*"
    return SpecifierSet(text)


def _python_spec(data: dict[str, Any], path: Path, *, required: bool) -> str | None:
    """Read a Python version request and reject malformed specifiers."""
    from packaging.specifiers import InvalidSpecifier

    value = _optional_string(data, "python", path)
    if value is None:
        if required:
            raise InstallConfigError(
                f"{path}: 'python' is required; write a version such as '3.11' "
                "or a range such as '>=3.10,<3.13'"
            )
        return None
    try:
        python_specifier(value)
    except InvalidSpecifier as exc:
        raise InstallConfigError(
            f"{path}: invalid 'python' request {value!r}: {exc}"
        ) from exc
    return value


@dataclass(frozen=True)
class TargetSettings:
    """Install settings shared by components and targets."""

    lock: str | None = None
    core: bool = True
    generate_extra: bool = True
    extra: str | None = None
    description: str | None = None
    index_url: str | None = None
    extra_index_urls: tuple[str, ...] = ()
    index_strategy: str | None = None
    manylinux: str = "2_31"


def _target_settings(data: dict[str, Any], path: Path, name: str) -> TargetSettings:
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
    index_strategy = _optional_string(data, "index-strategy", path)
    if index_strategy is not None and index_strategy not in INDEX_STRATEGIES:
        raise InstallConfigError(
            f"{path}: 'index-strategy' must be one of {', '.join(INDEX_STRATEGIES)}"
        )
    return TargetSettings(
        lock=_optional_string(data, "lock", path),
        core=core,
        generate_extra=generate_extra,
        extra=extra,
        description=_optional_string(data, "description", path),
        index_url=_optional_string(data, "index-url", path),
        extra_index_urls=_string_list(data, "extra-index-urls", path),
        index_strategy=index_strategy,
        manylinux=manylinux,
    )


@dataclass(frozen=True)
class Component:
    """One install boundary declared by ``component.toml``."""

    name: str
    kind: str
    path: Path
    manifest: Path
    probe: str
    python: str | None
    requires: tuple[str, ...]
    imports: tuple[str, ...]
    env_conflicts: tuple[str, ...]
    placements: tuple[str, ...]
    default_variant: str | None
    variant_required: bool
    dependencies: tuple[str, ...]
    optional: dict[str, tuple[str, ...]]
    overrides: tuple[Path, ...]
    docs: str | None
    manifest_sha256: str
    settings: TargetSettings = TargetSettings()

    @property
    def manifest_path(self) -> Path:
        """Return the manifest path."""
        return self.manifest

    @property
    def default_placement(self) -> str:
        """Return where a target installs the component unless it says otherwise.

        Targets write ``placement`` only for ``remote`` components, so a
        component that can be installed locally always defaults to the
        target's own environment.
        """
        return "in-env" if "in-env" in self.placements else self.placements[0]

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
    """How a target places one component."""

    placement: str | None = None
    variant: str | None = None


@dataclass(frozen=True)
class Target:
    """One install target: a component installed alone, or a composition."""

    name: str
    path: Path
    display_path: str
    python: str
    components: dict[str, Selection]
    dependencies: tuple[str, ...]
    index_url: str | None
    extra_index_urls: tuple[str, ...]
    index_strategy: str | None
    lock: str | None
    core: bool
    generate_extra: bool
    extra: str | None
    description: str | None
    manylinux: str = "2_31"
    default_lock_dir: str = "installs/locks"

    @property
    def relative_path(self) -> str:
        """Return the file path messages name, relative to the checkout."""
        return self.display_path

    def lock_file(self, root: Path) -> Path:
        """Return the declared or conventional lock path."""
        if self.lock:
            return root / self.lock
        return root / self.default_lock_dir / f"{self.name}.lock"

    def lock_display(self) -> str:
        """Return the lock path relative to the repository root, for messages."""
        if self.lock:
            return self.lock
        return f"{self.default_lock_dir}/{self.name}.lock"


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
    if kind == "target":
        raise InstallConfigError(
            f"{path}: 'target' manifests live at installs/targets/<name>.toml"
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
            "directory for robots, models and toolkits"
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
    _reject_unknown(data, path, "component")
    if kind not in KINDS:
        raise InstallConfigError(f"{path}: 'kind' must be one of {', '.join(KINDS)}")
    probe = data.get("probe")
    if not isinstance(probe, str) or not probe:
        raise InstallConfigError(f"{path}: 'probe' must be a non-empty import path")
    python = _python_spec(data, path, required=False)
    placements: tuple[str, ...] = () if kind == "deps" else _placement_list(data, path)
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
        requires=_string_list(data, "requires", path),
        imports=_string_list(data, "imports", path),
        env_conflicts=_string_list(data, "env_conflicts", path),
        placements=placements,
        default_variant=default_variant,
        variant_required=variant_required,
        dependencies=_dependency_list(data, "dependencies", path),
        optional=optional,
        overrides=overrides,
        docs=_optional_string(data, "docs", path),
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        settings=_target_settings(data, path, name),
    )


def _selections(data: dict[str, Any], path: Path) -> dict[str, Selection]:
    raw_components = data.get("components", {})
    if not isinstance(raw_components, dict):
        raise InstallConfigError(f"{path}: 'components' must be a table")
    components: dict[str, Selection] = {}
    for component_name, raw in raw_components.items():
        if not isinstance(raw, dict):
            raise InstallConfigError(
                f"{path}: components.{component_name} must be a table"
            )
        unknown = sorted(set(raw) - {"placement", "variant"})
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
        components[component_name] = Selection(placement=placement, variant=variant)
    return components


def _default_lock_dir(path: Path) -> str:
    """Return the lock directory beside the target file's root."""
    return f"{path.parent.parent.name}/locks"


def load_target(path: Path) -> Target:
    """Load and validate one target manifest."""
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    _reject_unknown(data, path, "target")
    if path.stem != name:
        raise InstallConfigError(
            f"{path}: name {name!r} must match its file name {path.stem!r}"
        )
    kind = data.get("kind")
    if kind != "target":
        raise InstallConfigError(f'{path}: target manifests declare kind = "target"')
    python = _python_spec(data, path, required=True)
    settings = _target_settings(data, path, name)
    return Target(
        name=name,
        path=path,
        display_path=f"{path.parent.parent.name}/{path.parent.name}/{path.name}",
        python=python,
        components=_selections(data, path),
        dependencies=_dependency_list(data, "dependencies", path),
        index_url=settings.index_url,
        extra_index_urls=settings.extra_index_urls,
        index_strategy=settings.index_strategy,
        lock=settings.lock,
        core=settings.core,
        generate_extra=settings.generate_extra,
        extra=settings.extra,
        description=settings.description,
        manylinux=settings.manylinux,
        default_lock_dir=_default_lock_dir(path),
    )


def target_from_component(component: Component) -> Target:
    """Return the install target a component forms when installed by name."""
    if component.python is None:
        raise InstallConfigError(
            f"{component.manifest_path}: a component installable on its own needs "
            "'python'; add a version or a range"
        )
    settings = component.settings
    return Target(
        name=component.name,
        path=component.manifest,
        display_path=f"{component.path.name}/{component.manifest.name}",
        python=component.python,
        components={component.name: Selection()},
        dependencies=(),
        index_url=settings.index_url,
        extra_index_urls=settings.extra_index_urls,
        index_strategy=settings.index_strategy,
        lock=settings.lock,
        core=settings.core,
        generate_extra=settings.generate_extra,
        extra=settings.extra,
        description=settings.description,
        manylinux=settings.manylinux,
        default_lock_dir="installs/locks",
    )
