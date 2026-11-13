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

"""Profiles resolve into placement groups and actionable configuration errors."""

from rpent.install.manifest import Selection
from rpent.install.resolve import resolve


def _catalog(make_catalog, *components):
    return make_catalog(components=list(components))


def test_requires_closure_adds_components_with_default_placement(
    make_component, make_profile, make_catalog
):
    robot = make_component("alpha", requires=["sam3"])
    sam3 = make_component(
        "sam3", kind="capability", placements=("in-env", "external-env")
    )
    profile = make_profile("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot, sam3)

    resolution = resolve(profile, catalog)

    assert resolution.ok
    assert resolution.components["sam3"].placement == "in-env"
    assert resolution.environments() == {"alpha": ("alpha", "sam3")}


def test_default_variant_is_used_when_the_profile_omits_one(
    make_component, make_profile, make_catalog
):
    robot = make_component(
        "alpha",
        dependencies=["base-dep"],
        default_variant="standard",
        optional={"standard": ("standard-dep",)},
    )
    profile = make_profile("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(profile, catalog)

    assert resolution.ok
    assert resolution.components["alpha"].variant == "standard"
    assert resolution.dependencies_for("alpha") == ("base-dep", "standard-dep")


def test_required_variant_must_be_selected(make_component, make_profile, make_catalog):
    robot = make_component(
        "alpha",
        variant_required=True,
        optional={"standard": ("standard-dep",), "pro": ("pro-dep",)},
    )
    profile = make_profile("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert any("requires a variant" in error for error in resolution.errors)


def test_external_placement_uses_named_environment(
    make_component, make_profile, make_catalog
):
    molmo = make_component(
        "molmo",
        kind="capability",
        placements=("in-env", "external-env"),
        default_placement="external-env",
    )
    profile = make_profile("flash", {"molmo": Selection(profile="molmo")})
    external = make_profile("molmo", {"molmo": Selection()})
    catalog = make_catalog(components=[molmo], profiles={"molmo": external})

    resolution = resolve(profile, catalog)

    assert resolution.ok
    assert resolution.external_components()["molmo"].env == "molmo"
    assert resolution.nonempty_environments() == {"molmo": ("molmo",)}


def test_external_environment_must_exist_and_include_the_component(
    make_component, make_profile, make_catalog
):
    molmo = make_component(
        "molmo", kind="capability", placements=("in-env", "external-env")
    )
    profile = make_profile(
        "flash", {"molmo": Selection(placement="external-env", profile="molmo")}
    )
    unrelated = make_profile("unrelated", {})
    catalog = make_catalog(components=[molmo], profiles={"unrelated": unrelated})

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert any("envs/molmo.toml does not exist" in error for error in resolution.errors)


def test_external_profile_without_the_component_is_reported(
    make_component, make_profile, make_catalog
):
    molmo = make_component(
        "molmo", kind="capability", placements=("in-env", "external-env")
    )
    profile = make_profile(
        "flash", {"molmo": Selection(placement="external-env", profile="molmo")}
    )
    external = make_profile("molmo", {})
    catalog = make_catalog(components=[molmo], profiles={"molmo": external})

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert any(
        "does not install component 'molmo'" in error for error in resolution.errors
    )


def test_unknown_component_is_reported(make_component, make_profile, make_catalog):
    profile = make_profile("alpha", {"missing": Selection()})
    catalog = _catalog(make_catalog)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert "references unknown component 'missing'" in resolution.errors[0]


def test_unsupported_placement_falls_back_and_reports(
    make_component, make_profile, make_catalog
):
    robot = make_component("alpha", placements=("in-env",))
    profile = make_profile("alpha", {"alpha": Selection(placement="remote")})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert resolution.components["alpha"].placement == "in-env"
    assert "cannot use placement 'remote'" in resolution.errors[0]


def test_python_and_platform_ranges_are_checked(
    make_component, make_profile, make_catalog
):
    robot = make_component("alpha", python=">=3.12", platforms=("linux-x86_64",))
    profile = make_profile("alpha", {"alpha": Selection()}, platform="darwin-arm64")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert any("requires Python >=3.12" in error for error in resolution.errors)
    assert any("supports linux-x86_64" in error for error in resolution.errors)


def test_declared_conflict_in_one_environment_is_reported(
    make_component, make_profile, make_catalog
):
    alpha = make_component("alpha", env_conflicts=["beta"])
    beta = make_component("beta", env_conflicts=["alpha"])
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert "places 'alpha' and 'beta' in the same environment" in resolution.errors[0]
    assert "option 1: install beta in a separate environment" in resolution.errors[0]


def test_conflict_reaches_components_pulled_in_by_requires(
    make_component, make_profile, make_catalog
):
    robot = make_component("alpha", requires=["policy"])
    policy = make_component("policy", env_conflicts=["grounder"])
    grounder = make_component("grounder", env_conflicts=["policy"])
    profile = make_profile("shared", {"alpha": Selection(), "grounder": Selection()})
    catalog = _catalog(make_catalog, robot, policy, grounder)

    resolution = resolve(profile, catalog)

    assert not resolution.ok
    assert (
        "places 'grounder' and 'policy' in the same environment"
        in (resolution.errors[0])
    )


def test_conflict_suggests_moving_the_component_that_can_leave_the_environment(
    make_component, make_profile, make_catalog
):
    alpha = make_component(
        "alpha",
        env_conflicts=["beta"],
        placements=("in-env", "external-env"),
    )
    beta = make_component("beta", env_conflicts=["alpha"])
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(profile, catalog)

    assert (
        "option 1: move alpha to external-env in envs/shared.toml"
        in (resolution.errors[0])
    )


def test_declared_conflict_in_separate_environments_is_allowed(
    make_component, make_profile, make_catalog
):
    alpha = make_component("alpha", env_conflicts=["beta"])
    beta = make_component(
        "beta",
        env_conflicts=["alpha"],
        placements=("in-env", "external-env"),
    )
    profile = make_profile(
        "shared",
        {
            "alpha": Selection(),
            "beta": Selection(placement="external-env", profile="beta"),
        },
    )
    catalog = make_catalog(
        components=[alpha, beta],
        profiles={"beta": make_profile("beta", {"beta": Selection()})},
    )

    resolution = resolve(profile, catalog)

    assert resolution.ok


def test_incompatible_pins_are_reported(make_component, make_profile, make_catalog):
    alpha = make_component("alpha", dependencies=["torch==2.7.0"])
    beta = make_component("beta", dependencies=["torch==2.8.0"])
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(profile, catalog)

    assert any("conflicting pins for 'torch'" in error for error in resolution.errors)


def test_overlapping_specifiers_are_compatible(
    make_component, make_profile, make_catalog
):
    alpha = make_component("alpha", dependencies=["huggingface-hub>=0.24,<1"])
    beta = make_component("beta", dependencies=["huggingface-hub>=0.34,<2"])
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(profile, catalog).ok


def test_marker_scoped_pins_select_one_wheel_and_are_ignored(
    make_component, make_profile, make_catalog
):
    markers = ' ; python_version == "3.11"'
    alpha = make_component(
        "alpha", dependencies=[f"franky @ https://example.test/franky.whl{markers}"]
    )
    beta = make_component(
        "beta", dependencies=[f"franky @ https://example.test/franky.whl{markers}"]
    )
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(profile, catalog).ok


def test_different_url_pins_are_reported(make_component, make_profile, make_catalog):
    alpha = make_component("alpha", dependencies=["pkg @ https://a.test/pkg.whl"])
    beta = make_component("beta", dependencies=["pkg @ https://b.test/pkg.whl"])
    profile = make_profile("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert any(
        "conflicting pins for 'pkg'" in error
        for error in resolve(profile, catalog).errors
    )
