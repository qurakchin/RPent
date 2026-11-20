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

"""The checked-in components, environments, and locks agree with each other."""

from rpent.install.discovery import environment_names, requested_components
from rpent.install.lock import lock_path
from rpent.install.resolve import resolve


def test_every_component_manifest_lives_where_its_kind_declares_it(catalog):
    for name, component in sorted(catalog.components.items()):
        assert component.name == name
        expected = component.path / "component.toml"
        assert component.manifest == expected


def test_every_component_is_an_environment_next_to_minimal(catalog):
    # A component without a reachable environment cannot be installed; naming
    # the environment after the component is what makes it installable.
    assert set(environment_names(catalog.components)) == {
        "minimal",
        *catalog.components,
    }


def test_every_environment_resolves(catalog):
    for name in environment_names(catalog.components):
        resolution = resolve(requested_components(name, catalog.components), catalog)

        assert resolution.ok, f"environment {name!r}: {'; '.join(resolution.errors)}"
        assert resolution.name == name


def test_locks_live_under_tests_and_follow_the_environment_name(catalog):
    # A lock is an optional reproduction artifact. Keeping every one under
    # ``tests/locks`` gives the repository's install data one home and stops a
    # lock from being read as an installation input.
    assert not (catalog.root / "installs").exists()
    assert not (catalog.root / "tests" / "targets").exists()
    known = environment_names(catalog.components)
    locks = sorted((catalog.root / "tests" / "locks").glob("*.lock"))
    assert locks
    for path in locks:
        name = path.stem
        assert name in known, f"lock {path.name} names no checked-in environment"
        assert lock_path(catalog.root, name) == path


def test_repository_manifests_declare_the_robotwin_molmo_conflict(catalog):
    components = catalog.components

    assert "sim-robotwin" in components["model-molmo"].env_conflicts
    assert "model-molmo" in components["sim-robotwin"].env_conflicts
    # OpenPI follows Molmo's Transformers range, so they are compatible.
    assert "model-molmo" not in components["model-openpi"].env_conflicts
