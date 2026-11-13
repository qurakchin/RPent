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

"""Generate compatibility extras and uv conflicts from manifests and profiles.

The generated tables are a one-release compatibility alias for
``pip install -e ".[<extra>]"``. ``rpent-env`` is the supported entry point;
after the compatibility release, delete the generated block and this module.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from rpent.install.discovery import Catalog
from rpent.install.manifest import Component
from rpent.install.requirements import environment_dependencies
from rpent.install.resolve import resolve

BEGIN_MARKER = (
    "# --- BEGIN GENERATED EXTRAS: do not edit, run scripts/gen_extras.py ---"
)
END_MARKER = "# --- END GENERATED EXTRAS ---"
#: Profiles whose extra is a development alias and must not enter uv conflicts.
DEV_PROFILES = {"dev"}


@dataclass(frozen=True)
class GeneratedExtras:
    """The rendered pyproject block and its component membership."""

    text: str
    extras: dict[str, tuple[str, ...]]
    components: dict[str, frozenset[str]]
    conflicts: tuple[tuple[str, str], ...]


def _component_closure(component: Component, catalog: Catalog) -> tuple[str, ...]:
    seen: set[str] = set()
    dependencies: list[str] = []
    pending = [component.name]
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        current = catalog.components[name]
        dependencies.extend(current.dependencies_for(None))
        pending.extend(current.requires)
    return tuple(sorted(dict.fromkeys(dependencies)))


def _profile_extra(
    profile_name: str, catalog: Catalog
) -> tuple[tuple[str, ...], frozenset[str]]:
    profile = catalog.profiles[profile_name]
    resolution = resolve(profile, catalog)
    if not resolution.ok:
        raise ValueError(
            f"profile {profile_name!r} is invalid:\n" + "\n".join(resolution.errors)
        )
    dependencies = environment_dependencies(resolution, profile.name)
    members = frozenset(
        name
        for name, resolved in resolution.components.items()
        if resolved.placement == "in-env"
    )
    return tuple(sorted(dict.fromkeys(dependencies))), members


def generate(catalog: Catalog) -> GeneratedExtras:
    """Build the compatibility extras and conflict matrix."""
    extras: dict[str, tuple[str, ...]] = {}
    members: dict[str, frozenset[str]] = {}
    covered: set[str] = set()
    for name, profile in sorted(catalog.profiles.items()):
        if not profile.generate_extra or profile.extra is None:
            continue
        dependencies, components = _profile_extra(name, catalog)
        extras[profile.extra] = dependencies
        members[profile.extra] = components
        if name not in DEV_PROFILES:
            covered.update(components)
    for name, component in sorted(catalog.components.items()):
        if name in covered:
            continue
        extra = name
        if extra in extras:
            continue
        extras[extra] = _component_closure(component, catalog)
        members[extra] = frozenset({name})

    dev_extras = {
        profile.extra
        for name, profile in catalog.profiles.items()
        if name in DEV_PROFILES and profile.extra is not None
    }
    conflicts: set[tuple[str, str]] = set()
    for left, right in itertools.combinations(sorted(catalog.components), 2):
        if (
            right not in catalog.components[left].env_conflicts
            and left not in catalog.components[right].env_conflicts
        ):
            continue
        left_extras = {
            extra
            for extra, included in members.items()
            if left in included and extra not in dev_extras
        }
        right_extras = {
            extra
            for extra, included in members.items()
            if right in included and extra not in dev_extras
        }
        for first in sorted(left_extras):
            for second in sorted(right_extras):
                if first == second:
                    continue
                if (
                    members[first] <= members[second]
                    or members[second] <= members[first]
                ):
                    continue
                conflicts.add(tuple(sorted((first, second))))
    return GeneratedExtras(
        text=_render(extras, sorted(conflicts)),
        extras=extras,
        components=members,
        conflicts=tuple(sorted(conflicts)),
    )


def _render(
    extras: dict[str, tuple[str, ...]],
    conflicts: list[tuple[str, str]],
) -> str:
    lines = [
        BEGIN_MARKER,
        "[project.optional-dependencies]",
    ]
    for name in sorted(extras):
        lines.append(f"{name} = [")
        for dependency in extras[name]:
            lines.append(f"    {dependency!r},")
        lines.append("]")
    lines.extend(
        [
            "",
            "[tool.uv]",
            'prerelease = "allow"',
            "",
            "# Each profile pulls a separately pinned simulator or model runtime whose",
            "# Torch, Transformers, Tokenizers, or Diffusers versions are mutually",
            "# incompatible with the others. Generated from component env_conflicts.",
            "conflicts = [",
        ]
    )
    for left, right in conflicts:
        lines.append(f'    [{{ extra = "{left}" }}, {{ extra = "{right}" }}],')
    lines.append("]")
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def replace_block(pyproject: str, generated: GeneratedExtras) -> str:
    """Replace the marked block in ``pyproject`` with ``generated``."""
    if BEGIN_MARKER not in pyproject or END_MARKER not in pyproject:
        raise ValueError(
            "pyproject.toml is missing the generated extras markers; add:\n"
            f"{BEGIN_MARKER}\n{END_MARKER}"
        )
    start = pyproject.index(BEGIN_MARKER)
    end = pyproject.index(END_MARKER) + len(END_MARKER)
    return pyproject[:start] + generated.text.rstrip("\n") + pyproject[end:]
