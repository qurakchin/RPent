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

"""Targets resolve into placement groups and actionable configuration errors."""

from rpent.install.manifest import Selection
from rpent.install.resolve import resolve


def _catalog(make_catalog, *components):
    return make_catalog(components=list(components))


def test_requires_closure_adds_components_with_default_placement(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", requires=["sam3"])
    sam3 = make_component("sam3", kind="model", placements=("in-env", "remote"))
    target = make_target("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot, sam3)

    resolution = resolve(target, catalog)

    assert resolution.ok
    assert resolution.components["sam3"].placement == "in-env"
    assert sorted(resolution.main_installed()) == ["alpha", "sam3"]


def test_mutual_requires_is_a_symmetric_closure(
    make_component, make_target, make_catalog
):
    # `requires` describes co-installation, which is symmetric; a mutual pair
    # must resolve once per component instead of being rejected as a cycle.
    alpha = make_component("alpha", requires=["beta"])
    beta = make_component("beta", requires=["alpha"])
    target = make_target("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert resolution.ok
    assert sorted(resolution.main_installed()) == ["alpha", "beta"]


def test_default_variant_is_used_when_the_target_omits_one(
    make_component, make_target, make_catalog
):
    robot = make_component(
        "alpha",
        dependencies=["base-dep"],
        default_variant="standard",
        optional={"standard": ("standard-dep",)},
    )
    target = make_target("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(target, catalog)

    assert resolution.ok
    assert resolution.components["alpha"].variant == "standard"
    assert resolution.components["alpha"].dependencies() == (
        "base-dep",
        "standard-dep",
    )


def test_required_variant_must_be_selected(make_component, make_target, make_catalog):
    robot = make_component(
        "alpha",
        variant_required=True,
        optional={"standard": ("standard-dep",), "pro": ("pro-dep",)},
    )
    target = make_target("alpha", {"alpha": Selection()})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert any("requires a variant" in error for error in resolution.errors)


def test_deps_component_is_listed_once_per_environment(
    make_component, make_target, make_catalog
):
    rlinf = make_component("rlinf", kind="deps")
    alpha = make_component("alpha", requires=["rlinf"])
    beta = make_component("beta", requires=["rlinf"])
    target = make_target("sim", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, rlinf, alpha, beta)

    resolution = resolve(target, catalog)

    assert resolution.ok
    assert resolution.deps == ["rlinf"]
    assert sorted(resolution.main_installed()) == ["alpha", "beta", "rlinf"]


def test_deps_component_joins_its_consumers_environment(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", requires=["rlinf"])
    model = make_component("molmo", kind="model", requires=["rlinf"])
    rlinf = make_component("rlinf", kind="deps")
    target = make_target("flash", {"alpha": Selection(), "molmo": Selection()})
    catalog = _catalog(make_catalog, rlinf, robot, model)

    resolution = resolve(target, catalog)

    assert resolution.ok
    # Two consumers in one environment pull the deps component in once; it is
    # not a service with an endpoint of its own.
    assert resolution.deps == ["rlinf"]
    assert sorted(resolution.main_installed()) == ["alpha", "molmo", "rlinf"]


def test_remote_placement_installs_no_environment(
    make_component, make_target, make_catalog
):
    molmo = make_component(
        "molmo",
        kind="model",
        placements=("in-env", "remote"),
    )
    target = make_target("flash", {"molmo": Selection(placement="remote")})
    catalog = make_catalog(components=[molmo])

    resolution = resolve(target, catalog)

    assert resolution.ok
    # A remote component installs nothing locally: it has no dependencies to
    # render and must not be probed.
    assert resolution.main_installed() == {}


def test_remote_consumer_cannot_pull_in_a_deps_component(
    make_component, make_target, make_catalog
):
    molmo = make_component(
        "molmo",
        kind="model",
        placements=("in-env", "remote"),
        requires=["rlinf"],
    )
    rlinf = make_component("rlinf", kind="deps")
    target = make_target("flash", {"molmo": Selection(placement="remote")})
    catalog = _catalog(make_catalog, molmo, rlinf)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert any(
        "requires deps component 'rlinf' but is placed remotely" in error
        for error in resolution.errors
    )


def test_unknown_component_is_reported(make_component, make_target, make_catalog):
    target = make_target("alpha", {"missing": Selection()})
    catalog = _catalog(make_catalog)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert "references unknown component 'missing'" in resolution.errors[0]


def test_unsupported_placement_falls_back_and_reports(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", placements=("in-env",))
    target = make_target("alpha", {"alpha": Selection(placement="remote")})
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert resolution.components["alpha"].placement == "in-env"
    assert "cannot use placement 'remote'" in resolution.errors[0]


def test_a_range_the_components_do_not_support_is_reported(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", python=">=3.12")
    target = make_target("alpha", {"alpha": Selection()}, python="3.11")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert resolution.python is None
    assert any(
        "requests Python 3.11" in error and "alpha: Python >=3.12" in error
        for error in resolution.errors
    )


def test_a_range_resolves_to_the_newest_supported_minor(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", python=">=3.10,<3.12")
    target = make_target("alpha", {"alpha": Selection()}, python=">=3.10,<3.13")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(target, catalog)

    assert resolution.ok
    assert resolution.python == "3.11"


def test_declared_conflict_in_one_environment_is_reported(
    make_component, make_target, make_catalog
):
    alpha = make_component("alpha", env_conflicts=["beta"])
    beta = make_component("beta", env_conflicts=["alpha"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert "places 'alpha' and 'beta' in the same environment" in resolution.errors[0]
    assert (
        "split alpha and beta into separate targets and connect them by endpoint"
        in resolution.errors[0]
    )


def test_conflict_reaches_components_pulled_in_by_requires(
    make_component, make_target, make_catalog
):
    robot = make_component("alpha", requires=["policy"])
    policy = make_component("policy", env_conflicts=["grounder"])
    grounder = make_component("grounder", env_conflicts=["policy"])
    target = make_target("shared", {"alpha": Selection(), "grounder": Selection()})
    catalog = _catalog(make_catalog, robot, policy, grounder)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert (
        "places 'grounder' and 'policy' in the same environment"
        in (resolution.errors[0])
    )


def test_conflict_suggests_moving_the_component_that_can_leave_the_environment(
    make_component, make_target, make_catalog
):
    alpha = make_component(
        "alpha",
        env_conflicts=["beta"],
        placements=("in-env", "remote"),
    )
    beta = make_component("beta", env_conflicts=["alpha"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert (
        "option 1: place alpha remotely in installs/targets/shared.toml"
        in (resolution.errors[0])
    )


def test_two_components_cannot_override_one_package(
    make_component, make_target, make_catalog, tmp_path
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("# keep numpy below 2\nnumpy<2\n", encoding="utf-8")
    right.write_text("numpy<3\n", encoding="utf-8")
    alpha = make_component("alpha", overrides=[left])
    beta = make_component("beta", overrides=[right])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    # uv merges the override files, so the winner would depend on file order.
    assert "both override 'numpy'" in resolution.errors[0]
    assert "merge the override files" in resolution.errors[0]


def test_marker_scoped_overrides_leave_the_choice_to_uv(
    make_component, make_target, make_catalog, tmp_path
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("numpy<2\n", encoding="utf-8")
    right.write_text('numpy<3; sys_platform == "win32"\n', encoding="utf-8")
    alpha = make_component("alpha", overrides=[left])
    beta = make_component("beta", overrides=[right])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    # The two lines select different targets, so the resolver decides which
    # one applies instead of the check reporting a duplicate.
    assert resolve(target, catalog).ok


def test_target_cannot_repeat_a_component_dependency(
    make_component, make_target, make_catalog
):
    alpha = make_component("alpha", dependencies=["numpy>=2"])
    target = make_target(
        "shared",
        {"alpha": Selection()},
        dependencies=["numpy<3"],
    )
    catalog = _catalog(make_catalog, alpha)

    resolution = resolve(target, catalog)

    assert not resolution.ok
    assert "component 'alpha' already requires it" in resolution.errors[0]


def test_target_dependencies_outside_the_closure_are_allowed(
    make_component, make_target, make_catalog
):
    alpha = make_component("alpha", dependencies=["numpy>=2"])
    target = make_target(
        "shared",
        {"alpha": Selection()},
        dependencies=["pytest"],
    )
    catalog = _catalog(make_catalog, alpha)

    assert resolve(target, catalog).ok


def test_declared_conflict_in_separate_environments_is_allowed(
    make_component, make_target, make_catalog
):
    alpha = make_component("alpha", env_conflicts=["beta"])
    beta = make_component(
        "beta",
        env_conflicts=["alpha"],
        placements=("in-env", "remote"),
    )
    target = make_target(
        "shared",
        {
            "alpha": Selection(),
            "beta": Selection(placement="remote"),
        },
    )
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert resolution.ok


def test_incompatible_pins_are_reported(make_component, make_target, make_catalog):
    alpha = make_component("alpha", dependencies=["torch==2.7.0"])
    beta = make_component("beta", dependencies=["torch==2.8.0"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(target, catalog)

    assert any("conflicting pins for 'torch'" in error for error in resolution.errors)


def test_overlapping_specifiers_are_compatible(
    make_component, make_target, make_catalog
):
    alpha = make_component("alpha", dependencies=["huggingface-hub>=0.24,<1"])
    beta = make_component("beta", dependencies=["huggingface-hub>=0.34,<2"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(target, catalog).ok


def test_range_pins_are_left_to_uv(make_component, make_target, make_catalog):
    # `>1.0` and `<1.0.1` overlap at 1.0.post1; sampling boundaries used to
    # report a false conflict, so ranges are not compared statically.
    alpha = make_component("alpha", dependencies=["pkg>1.0"])
    beta = make_component("beta", dependencies=["pkg<1.0.1"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(target, catalog).ok


def test_marker_scoped_pins_select_one_wheel_and_are_ignored(
    make_component, make_target, make_catalog
):
    markers = ' ; python_version == "3.11"'
    alpha = make_component(
        "alpha", dependencies=[f"franky @ https://example.test/franky.whl{markers}"]
    )
    beta = make_component(
        "beta", dependencies=[f"franky @ https://example.test/franky.whl{markers}"]
    )
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(target, catalog).ok


def test_different_url_pins_are_reported(make_component, make_target, make_catalog):
    alpha = make_component("alpha", dependencies=["pkg @ https://a.test/pkg.whl"])
    beta = make_component("beta", dependencies=["pkg @ https://b.test/pkg.whl"])
    target = make_target("shared", {"alpha": Selection(), "beta": Selection()})
    catalog = _catalog(make_catalog, alpha, beta)

    assert any(
        "conflicting pins for 'pkg'" in error
        for error in resolve(target, catalog).errors
    )
