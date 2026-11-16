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

"""Compatibility extras in ``pyproject.toml`` mirror the checked-in manifests."""

import tomllib

from rpent.install.extras import replace_block, repository_extras


def test_repository_manifests_declare_the_robotwin_molmo_conflict(catalog):
    components = catalog.components

    assert "robotwin" in components["molmo"].env_conflicts
    assert "molmo" in components["robotwin"].env_conflicts
    # OpenPI follows Molmo's Transformers range, so they are compatible.
    assert "molmo" not in components["openpi"].env_conflicts


def test_repository_extras_keep_only_the_real_molmo_conflict(catalog):
    generated = repository_extras(catalog)

    # RoboTwin pins transformers 4.51.3 and Molmo needs >=4.57. LIBERO and
    # OpenPI resolve transformers 4.57.6, which satisfies Molmo.
    assert ("molmo", "robotwin") in generated.conflicts
    assert ("libero", "molmo") not in generated.conflicts


def test_repository_pyproject_keeps_the_renamed_extra_name(catalog):
    project = tomllib.loads(
        (catalog.root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    extras = project["optional-dependencies"]

    # `pip install -e ".[robodojo-sim]"` predates the component rename.
    assert "robodojo-sim" in extras
    assert extras["robodojo-sim"] == extras["robodojo"]


def test_repository_pyproject_matches_the_generated_block(catalog):
    path = catalog.root / "pyproject.toml"
    current = path.read_text(encoding="utf-8")

    # `rpent-install extras --check` compares the same text, so a stale block
    # fails here before CI reaches the static job.
    assert replace_block(current, repository_extras(catalog)) == current
