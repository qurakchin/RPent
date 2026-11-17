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

"""The checked-in components and profiles agree with each other."""

from rpent.install.requirements import read_core_dependencies
from rpent.install.resolve import resolve


def test_every_component_manifest_lives_where_its_kind_declares_it(catalog):
    for name, component in sorted(catalog.components.items()):
        assert component.name == name
        if component.kind == "deps":
            expected = catalog.root / "installs" / "deps" / f"{name}.toml"
        else:
            expected = component.path / "component.toml"
        assert component.manifest == expected


def test_every_profile_selects_known_components(catalog):
    for name, profile in sorted(catalog.profiles.items()):
        missing = sorted(set(profile.components) - set(catalog.components))
        assert not missing, f"profile {name!r} selects unknown components {missing}"


def test_every_profile_resolves(catalog):
    for name, profile in sorted(catalog.profiles.items()):
        core = read_core_dependencies(catalog.root) if profile.core else ()
        resolution = resolve(profile, catalog, core_dependencies=core)

        assert resolution.ok, f"profile {name!r}: {'; '.join(resolution.errors)}"
