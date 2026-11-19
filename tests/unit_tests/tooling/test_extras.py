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

"""Compatibility extras mirror targets, component closures, and conflicts."""

import pytest

from rpent.install.manifest import Selection
from tests.tooling.extras import BEGIN_MARKER, END_MARKER, generate, replace_block


@pytest.fixture
def catalog(make_component, make_target, make_catalog):
    alpha = make_component("alpha", dependencies=["alpha-dep"], env_conflicts=["beta"])
    beta = make_component("beta", dependencies=["beta-dep"], env_conflicts=["alpha"])
    gamma = make_component(
        "gamma", kind="model", dependencies=["gamma-dep"], requires=["delta"]
    )
    delta = make_component("delta", kind="model", dependencies=["delta-dep"])
    catalog_targets = {
        "alpha": make_target(
            "alpha",
            {"alpha": Selection()},
            generate_extra=True,
            extra="alpha",
        ),
        "beta": make_target(
            "beta",
            {"beta": Selection()},
            generate_extra=True,
            extra="beta",
        ),
        "deep": make_target(
            "deep",
            {"gamma": Selection()},
            generate_extra=True,
            extra="deep",
        ),
        "dev": make_target(
            "dev",
            {},
            generate_extra=True,
            extra="test",
            dependencies=("pytest",),
        ),
    }
    return make_catalog(
        components=[alpha, beta, gamma, delta],
        targets=catalog_targets,
    )


def test_extras_cover_targets_components_and_dev(catalog):
    generated = generate(catalog)

    assert generated.extras["alpha"] == ("alpha-dep",)
    assert generated.extras["beta"] == ("beta-dep",)
    assert generated.extras["deep"] == ("delta-dep", "gamma-dep")
    assert generated.extras["test"] == ("pytest",)
    assert generated.components["alpha"] == frozenset({"alpha"})


def test_conflicts_pair_incompatible_extras_and_skip_dev(catalog):
    generated = generate(catalog)

    assert generated.conflicts == (("alpha", "beta"),)
    assert "[tool.uv]" in generated.text
    assert "conflicts = [" in generated.text
    assert '{ extra = "alpha" }, { extra = "beta" }' in generated.text


def test_alias_shares_the_target_extra(catalog):
    generated = generate(catalog, aliases={"old-alpha": "alpha"})

    assert generated.extras["old-alpha"] == generated.extras["alpha"]
    assert generated.components["old-alpha"] == generated.components["alpha"]


def test_alias_without_target_is_ignored(catalog):
    generated = generate(catalog, aliases={"old-missing": "missing"})

    assert "old-missing" not in generated.extras


def test_replace_block_requires_markers_and_is_idempotent(catalog):
    generated = generate(catalog)
    document = f"before\n{BEGIN_MARKER}\nold\n{END_MARKER}\nafter\n"

    replaced = replace_block(document, generated)

    assert replaced.startswith("before\n")
    assert replaced.endswith("\nafter\n")
    assert "old" not in replaced
    assert replace_block(replaced, generated) == replaced

    with pytest.raises(ValueError, match="missing the generated extras markers"):
        replace_block("no markers", generated)
