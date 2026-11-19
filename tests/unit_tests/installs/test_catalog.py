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

"""The checked-in components and targets agree with each other."""

from rpent.install.resolve import resolve


def test_every_component_manifest_lives_where_its_kind_declares_it(catalog):
    for name, component in sorted(catalog.components.items()):
        assert component.name == name
        expected = component.path / "component.toml"
        assert component.manifest == expected


def test_every_target_selects_known_components(catalog):
    for name, target in sorted(catalog.targets.items()):
        missing = sorted(set(target.components) - set(catalog.components))
        assert not missing, f"target {name!r} selects unknown components {missing}"


def test_every_robot_is_selected_by_a_target(catalog):
    # Installing a robot means choosing the environment it runs in, which only
    # a target file declares; a robot that no target selects cannot be
    # installed at all.
    for name, component in sorted(catalog.components.items()):
        if component.kind != "robot":
            continue
        providers = [
            target.name
            for target in catalog.targets.values()
            if name in target.components
        ]
        assert providers, f"robot component {name!r} has no install target"


def test_a_robot_target_is_a_file_not_the_component_manifest(catalog):
    # A same-name target is an explicit override, never the synthesized target
    # a non-robot component would get.
    for name, component in sorted(catalog.components.items()):
        if component.kind != "robot":
            continue
        target = catalog.targets.get(name)
        if target is None:
            continue
        assert target.path != component.manifest
        assert name in target.components


def test_every_target_resolves(catalog):
    for name, target in sorted(catalog.targets.items()):
        resolution = resolve(target, catalog)

        assert resolution.ok, f"target {name!r}: {'; '.join(resolution.errors)}"


def test_locks_live_under_tests_and_follow_the_target_name(catalog):
    # A lock is an optional reproduction artifact. Keeping every one under
    # ``tests/locks`` gives the repository's install data one home and stops a
    # manifest from naming a second path for the same target.
    assert not (catalog.root / "installs" / "locks").exists()
    for name, target in sorted(catalog.targets.items()):
        assert target.lock_file(catalog.root) == (
            catalog.root / "tests" / "locks" / f"{name}.lock"
        )
        assert target.lock_display() == f"tests/locks/{name}.lock"


def test_repository_manifests_declare_the_robotwin_molmo_conflict(catalog):
    components = catalog.components

    assert "sim-robotwin" in components["model-molmo"].env_conflicts
    assert "model-molmo" in components["sim-robotwin"].env_conflicts
    # OpenPI follows Molmo's Transformers range, so they are compatible.
    assert "model-molmo" not in components["model-openpi"].env_conflicts
