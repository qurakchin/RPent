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

"""The compatibility extras and the component manifests describe one fact.

``pyproject.toml`` keeps extras for the robot slices no profile selects yet, so
their dependencies are written twice: once in the extra and once in the
component manifest. This test fails when the two drift apart. Delete it
together with the extras once every slice has a profile.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from rpent.install.discovery import discover_components

ROOT = Path(__file__).resolve().parents[3]

#: Compatibility extra -> the component whose dependency closure it must equal.
EXTRA_COMPONENTS = {
    "franka": "franka",
    "robocasa": "robocasa",
    "robodojo-sim": "robodojo",
    "robotwin": "robotwin",
    "sam3": "sam3",
    "yam": "yam",
}

#: Extras that do not mirror a component.
EXTRA_ONLY = {"test"}


def _closure(components, name: str) -> set[str]:
    """Return the dependencies of ``name`` and of everything it requires."""
    seen: set[str] = set()
    pending = [name]
    requirements: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        component = components[current]
        requirements.update(component.dependencies)
        pending.extend(component.requires)
    return requirements


def test_every_compatibility_extra_mirrors_one_component():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]

    assert set(extras) == set(EXTRA_COMPONENTS) | EXTRA_ONLY


def test_compatibility_extras_match_their_component_closure():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    components = discover_components(ROOT)

    for extra, component in EXTRA_COMPONENTS.items():
        expected = _closure(components, component)
        recorded = set(extras[extra])
        assert recorded == expected, (
            f"extra {extra!r} and component {component!r} disagree: "
            f"only in the extra: {sorted(recorded - expected)}; "
            f"only in the manifest: {sorted(expected - recorded)}"
        )
