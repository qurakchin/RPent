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
``pip install -e ".[<extra>]"``. ``rpent-install`` is the supported entry point;
after the compatibility release, delete the generated block and this module.

Usage::

    rpent-install extras --write
    rpent-install extras --check   # CI
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.manifest import Component
from rpent.install.requirements import environment_dependencies
from rpent.install.resolve import resolve

BEGIN_MARKER = (
    "# --- BEGIN GENERATED EXTRAS: do not edit, run `rpent-install extras --write` ---"
)
END_MARKER = "# --- END GENERATED EXTRAS ---"
#: Profiles whose extra is a development alias and must not enter uv conflicts.
DEV_PROFILES = {"dev"}
#: Pre-migration extras whose component or profile now has a different name.
#: They keep working for the compatibility release.
EXTRA_ALIASES = {"robodojo-sim": "robodojo"}
#: Extras published before the component split. A rename may add an alias but
#: must not drop a name users already install.
LEGACY_EXTRAS = (
    "cosmos3",
    "cosmos_policy",
    "dual-franka",
    "fast_wam",
    "franka",
    "geometry-eval",
    "libero",
    "libero-openpi-external",
    "libero-plus",
    "libero-pro",
    "libero-pro-flywheel",
    "libero-pro-molmo",
    "molmo",
    "openpi",
    "rlinf",
    "robocasa",
    "robodojo",
    "robodojo-sim",
    "robotwin",
    "sam3",
    "test",
    "yam",
)


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


def generate(
    catalog: Catalog,
    *,
    aliases: Mapping[str, str] | None = None,
) -> GeneratedExtras:
    """Build the compatibility extras and conflict matrix.

    ``aliases`` maps a legacy extra name to the current one so a repository
    rename does not break instructions users already have. Aliases share the
    target's dependencies and component membership.
    """
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
        extra = name
        if extra in extras:
            continue
        # A model or deps component keeps its own compatibility extra even when
        # a profile installs it, so ``pip install -e ".[sam3]"`` and
        # ``pip install -e ".[rlinf]"`` keep working during the migration.
        if name in covered and component.kind not in {"model", "deps"}:
            continue
        extras[extra] = _component_closure(component, catalog)
        members[extra] = frozenset({name})

    for alias, extra in sorted((aliases or {}).items()):
        if extra in extras:
            extras.setdefault(alias, extras[extra])
            members.setdefault(alias, members[extra])

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


def repository_extras(catalog: Catalog) -> GeneratedExtras:
    """Return generated extras with the repository's compatibility aliases."""
    generated = generate(catalog, aliases=EXTRA_ALIASES)
    missing = [name for name in LEGACY_EXTRAS if name not in generated.extras]
    if missing:
        raise SystemExit(
            "compatibility extras disappeared from the generated block: "
            + ", ".join(missing)
        )
    return generated


def main(argv: list[str] | None = None, *, root: Path) -> int:
    """Rewrite or verify the generated block in ``pyproject.toml``."""
    parser = argparse.ArgumentParser(
        prog="rpent-install extras",
        description="Regenerate the compatibility extras and uv conflicts.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write",
        action="store_true",
        help="rewrite the generated block in pyproject.toml",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="fail when pyproject.toml is out of date (default)",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=root / "pyproject.toml",
        help="pyproject.toml to update or verify",
    )
    args = parser.parse_args(argv)
    generated = repository_extras(discover(root))
    current = args.pyproject.read_text(encoding="utf-8")
    updated = replace_block(current, generated)
    if args.write:
        if updated != current:
            args.pyproject.write_text(updated, encoding="utf-8")
            print(f"updated {args.pyproject}")
        else:
            print(f"{args.pyproject} already up to date")
        return 0
    if updated != current:
        print(
            f"{args.pyproject} is out of date with component manifests; "
            "run `rpent-install extras --write`",
            file=sys.stderr,
        )
        return 1
    print(f"{args.pyproject} extras and conflicts are up to date")
    return 0
