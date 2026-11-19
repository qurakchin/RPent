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

Every component owns one directory below a root named after its kind, and its
name is ``<kind>-<directory>``: ``sim-example`` lives at
``components/sim/example``. The kind is a property of the directory, so a
manifest cannot disagree with where it lives and a target's component list
names exactly what it installs.

A target is a manifest without code: ``installs/targets/<name>.toml`` composes
components, ``tests/targets/`` serves only tests and CI. Targets may add
packages that belong to no component but never repeat a component's
declarations.
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
#: Component roots, relative to the checkout, by kind. A component's name is
#: ``<kind>-<directory name>``, which keeps every installable name unique across
#: roots without a separate namespace.
COMPONENT_DIRECTORIES = {
    "robot": "robots",
    "sim": "components/sim",
    "model": "components/models",
    "tool": "components/tools",
    "infra": "components/infra",
}
KINDS = tuple(COMPONENT_DIRECTORIES)
#: Hosts a component can declare. ``linux-x86_64`` is the only default: every
#: current runtime depends on Linux wheels, and macOS support is per component.
PLATFORMS = (
    "linux-x86_64",
    "linux-aarch64",
    "darwin-arm64",
    "darwin-x86_64",
)
DEFAULT_PLATFORMS = ("linux-x86_64",)
#: ``uv``'s multi-index strategies; see ``--index-strategy`` in ``uv pip compile``.
INDEX_STRATEGIES = ("first-index", "unsafe-first-match", "unsafe-best-match")
#: Python minors the repository supports, newest first. A component's range is
#: resolved to the highest minor in this list that every component accepts.
PYTHON_MINORS = ("3.12", "3.11", "3.10")
#: The newest glibc baseline a component needs. ``uv`` compiles a lock for the
#: newest baseline in the target's closure, and a newer baseline admits every
#: wheel an older one does.
DEFAULT_MANYLINUX = "2_31"
#: ``uv --python-platform`` value per host. Only the linux entries depend on the
#: glibc baseline.
PLATFORM_TAGS = {
    "linux-x86_64": "x86_64-manylinux_{baseline}",
    "linux-aarch64": "aarch64-manylinux_{baseline}",
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x86_64": "x86_64-apple-darwin",
}
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
            "probe",
            "python",
            "platforms",
            "manylinux",
            "requires",
            "imports",
            "env_conflicts",
            "dependencies",
            "overrides",
            "core",
            "description",
            "index-url",
            "extra-index-urls",
            "index-strategy",
        }
    ),
    "target": frozenset(
        {
            "schema",
            "name",
            "components",
            "dependencies",
            "core",
            "description",
            "index-url",
            "extra-index-urls",
            "index-strategy",
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


def python_specifier(value: str) -> "SpecifierSet":
    """Return the PEP 440 specification a Python request denotes.

    A bare version such as ``3.11`` means ``==3.11.*``: components mean the
    minor, not one patch release. A range is used as written.
    """
    from packaging.specifiers import SpecifierSet

    text = value.strip()
    if text[:1].isdigit():
        text = f"=={text}.*"
    return SpecifierSet(text)


def _python_spec(data: dict[str, Any], path: Path) -> str | None:
    """Read a Python version request and reject malformed specifiers."""
    from packaging.specifiers import InvalidSpecifier

    value = _optional_string(data, "python", path)
    if value is None:
        return None
    try:
        python_specifier(value)
    except InvalidSpecifier as exc:
        raise InstallConfigError(
            f"{path}: invalid 'python' request {value!r}: {exc}"
        ) from exc
    return value


def _platforms(data: dict[str, Any], path: Path) -> tuple[str, ...]:
    """Read the hosts a component installs on, defaulting to linux-x86_64."""
    declared = _string_list(data, "platforms", path) or DEFAULT_PLATFORMS
    unknown = sorted(set(declared) - set(PLATFORMS))
    if unknown:
        raise InstallConfigError(
            f"{path}: unknown platform(s) {', '.join(unknown)}; expected one of "
            f"{', '.join(PLATFORMS)}"
        )
    return tuple(sorted(set(declared)))


def _manylinux(data: dict[str, Any], path: Path) -> str:
    value = data.get("manylinux", DEFAULT_MANYLINUX)
    if not isinstance(value, str) or not _MANYLINUX.match(value):
        raise InstallConfigError(
            f"{path}: 'manylinux' must name a glibc baseline such as "
            f"{DEFAULT_MANYLINUX!r}"
        )
    return value


def _index_settings(
    data: dict[str, Any], path: Path
) -> tuple[str | None, tuple[str, ...], str | None]:
    index_strategy = _optional_string(data, "index-strategy", path)
    if index_strategy is not None and index_strategy not in INDEX_STRATEGIES:
        raise InstallConfigError(
            f"{path}: 'index-strategy' must be one of {', '.join(INDEX_STRATEGIES)}"
        )
    return (
        _optional_string(data, "index-url", path),
        _string_list(data, "extra-index-urls", path),
        index_strategy,
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
    dependencies: tuple[str, ...]
    overrides: tuple[Path, ...]
    manifest_sha256: str
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    manylinux: str = DEFAULT_MANYLINUX
    core: bool = True
    description: str | None = None
    index_url: str | None = None
    extra_index_urls: tuple[str, ...] = ()
    index_strategy: str | None = None

    @property
    def manifest_path(self) -> Path:
        """Return the manifest path."""
        return self.manifest


@dataclass(frozen=True)
class Target:
    """One install target: a component installed alone, or a composition."""

    name: str
    path: Path
    components: tuple[str, ...]
    dependencies: tuple[str, ...]
    index_url: str | None
    extra_index_urls: tuple[str, ...]
    index_strategy: str | None
    core: bool
    description: str | None

    def relative_path(self, root: Path) -> str:
        """Return the manifest path relative to the checkout, for messages.

        Every target names a file: the target manifest for a composition, and
        ``component.toml`` for a component installed under its own name. The
        caller supplies the checkout so a manifest cannot report a path that
        does not exist.
        """
        return self.path.relative_to(root).as_posix()

    def lock_file(self, root: Path) -> Path:
        """Return this target's optional reproduction lock.

        Locks are not installation inputs. Every checked-in lock lives under
        ``tests/locks`` so the repository's install data has one home, and the
        path follows the target name rather than a manifest field.
        """
        return root / "tests" / "locks" / f"{self.name}.lock"

    def lock_display(self) -> str:
        """Return the lock path relative to the repository root, for messages."""
        return f"tests/locks/{self.name}.lock"


def load_component(path: Path, kind: str) -> Component:
    """Load and validate one ``component.toml`` from a component root.

    ``kind`` comes from the root the manifest was discovered under; the name
    must then be ``<kind>-<directory>`` so a manifest cannot claim another
    root's component.
    """
    if kind not in COMPONENT_DIRECTORIES:
        raise InstallConfigError(
            f"{path}: unknown component kind {kind!r}; expected one of "
            f"{', '.join(KINDS)}"
        )
    data = _read_toml(path)
    _schema(data, path)
    name = _name(data, path)
    expected = f"{kind}-{path.parent.name}"
    if name != expected:
        raise InstallConfigError(
            f"{path}: name {name!r} must be {expected!r} so it matches the "
            f"{COMPONENT_DIRECTORIES[kind]}/ root and its directory"
        )
    return _component(data, path, name=name, kind=kind)


def _component(
    data: dict[str, Any],
    path: Path,
    *,
    name: str,
    kind: str,
) -> Component:
    """Build a component from parsed data, validating shared fields."""
    _reject_unknown(data, path, "component")
    probe = data.get("probe")
    if not isinstance(probe, str) or not probe:
        raise InstallConfigError(f"{path}: 'probe' must be a non-empty import path")
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
    core = data.get("core", True)
    if not isinstance(core, bool):
        raise InstallConfigError(f"{path}: 'core' must be a boolean")
    index_url, extra_index_urls, index_strategy = _index_settings(data, path)
    return Component(
        name=name,
        kind=kind,
        path=path.parent,
        manifest=path,
        probe=probe,
        python=_python_spec(data, path),
        requires=_string_list(data, "requires", path),
        imports=_string_list(data, "imports", path),
        env_conflicts=_string_list(data, "env_conflicts", path),
        dependencies=_dependency_list(data, "dependencies", path),
        overrides=overrides,
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        platforms=_platforms(data, path),
        manylinux=_manylinux(data, path),
        core=core,
        description=_optional_string(data, "description", path),
        index_url=index_url,
        extra_index_urls=extra_index_urls,
        index_strategy=index_strategy,
    )


def _components(data: dict[str, Any], path: Path) -> tuple[str, ...]:
    """Return the component names a target selects.

    The table's values must be empty: a component's own manifest decides what
    it installs, so an option here could only disagree with it.
    """
    raw = data.get("components", {})
    if not isinstance(raw, dict):
        raise InstallConfigError(f"{path}: 'components' must be a table")
    for component_name, entry in raw.items():
        if not isinstance(entry, dict):
            raise InstallConfigError(
                f"{path}: components.{component_name} must be a table"
            )
        if entry:
            raise InstallConfigError(
                f"{path}: components.{component_name} must be empty; "
                f"unexpected field(s): {', '.join(sorted(entry))}"
            )
    return tuple(sorted(raw))


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
    core = data.get("core", True)
    if not isinstance(core, bool):
        raise InstallConfigError(f"{path}: 'core' must be a boolean")
    index_url, extra_index_urls, index_strategy = _index_settings(data, path)
    return Target(
        name=name,
        path=path,
        components=_components(data, path),
        dependencies=_dependency_list(data, "dependencies", path),
        index_url=index_url,
        extra_index_urls=extra_index_urls,
        index_strategy=index_strategy,
        core=core,
        description=_optional_string(data, "description", path),
    )


def target_from_component(component: Component) -> Target:
    """Return the install target a component forms when installed by name."""
    return Target(
        name=component.name,
        path=component.manifest,
        components=(component.name,),
        dependencies=(),
        index_url=component.index_url,
        extra_index_urls=component.extra_index_urls,
        index_strategy=component.index_strategy,
        core=component.core,
        description=component.description,
    )
