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

"""The checked-in components, targets and locks agree with each other."""

from rpent.install.lock_coverage import lock_problems
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


def test_every_target_selects_known_components(catalog):
    for name, target in sorted(catalog.targets.items()):
        missing = sorted(set(target.components) - set(catalog.components))
        assert not missing, f"target {name!r} selects unknown components {missing}"


def test_every_target_resolves(catalog):
    for name, target in sorted(catalog.targets.items()):
        resolution = resolve(target, catalog)

        assert resolution.ok, f"target {name!r}: {'; '.join(resolution.errors)}"


def test_every_target_declares_the_lock_it_ships(catalog):
    for name, target in sorted(catalog.targets.items()):
        # An undeclared lock defaults to ``locks/<name>.lock`` beside the
        # target directory, so user and test targets keep the same layout.
        assert target.lock_file(catalog.root).is_file(), (
            f"target {name!r} needs {target.lock_display()}"
        )


def test_every_lock_covers_its_target(catalog):
    for name, target in sorted(catalog.targets.items()):
        core = read_core_dependencies(catalog.root) if target.core else ()
        resolution = resolve(target, catalog, core_dependencies=core)
        problems = lock_problems(
            target,
            resolution,
            catalog.root,
            core_dependencies=core,
        )

        assert not problems, f"target {name!r}: {'; '.join(problems)}"
