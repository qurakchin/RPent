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

"""The checked-in component manifests agree with each other and with the tree."""

import pytest

from rpent.install.manifest import KINDS
from rpent.install.requirements import read_core_dependencies
from rpent.install.resolve import resolve


def test_every_component_manifest_lives_where_its_name_declares_it(catalog):
    for name, component in sorted(catalog.components.items()):
        assert component.name == name
        assert name.startswith(f"{component.kind}-")
        if component.kind == "infra":
            assert component.path is None
            assert component.manifest == catalog.root / "installs" / f"{name}.toml"
        else:
            assert component.manifest == component.path / "component.toml"


def test_every_kind_has_at_least_one_component(catalog):
    kinds = {component.kind for component in catalog.components.values()}

    assert kinds == set(KINDS)


def test_every_component_resolves_with_its_requires_closure(catalog):
    core = read_core_dependencies(catalog.root)

    for name in sorted(catalog.components):
        resolution = resolve([name], catalog, core_dependencies=core)

        assert resolution.ok, f"component {name!r}: {'; '.join(resolution.errors)}"
        assert name in resolution.components


@pytest.mark.parametrize("kind", ["robot", "sim", "model", "tool"])
def test_every_in_tree_probe_names_an_existing_module(catalog, kind):
    # A probe that names checkout code must point inside the component's own
    # directory, so a moved or renamed slice fails here instead of at install
    # time. Probes such as `openpi` name the installed upstream distribution and
    # are checked by the install itself.
    for component in catalog.components.values():
        if component.kind != kind:
            continue
        first = component.probe.split(".")[0]
        if first not in {"robots", "components"}:
            continue
        path = catalog.root / component.probe.replace(".", "/")
        assert path.is_dir() or path.with_suffix(".py").is_file(), (
            f"{component.name}: probe {component.probe!r} is not a module in the "
            "checkout"
        )
        assert path.is_relative_to(component.path), (
            f"{component.name}: probe {component.probe!r} points outside "
            f"{component.path}"
        )


def test_core_dependencies_are_declared(catalog):
    assert read_core_dependencies(catalog.root)
