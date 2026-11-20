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

"""Requested components resolve into environments and actionable errors."""

from rpent.install.resolve import resolve


def _catalog(make_catalog, *components):
    return make_catalog(components=list(components))


def test_requires_closure_adds_components_to_the_environment(
    make_component, make_catalog
):
    robot = make_component("robot-alpha", requires=["model-sam3"])
    sam3 = make_component("model-sam3")
    catalog = _catalog(make_catalog, robot, sam3)

    resolution = resolve(("robot-alpha",), catalog)

    assert resolution.ok
    assert sorted(resolution.components) == ["model-sam3", "robot-alpha"]


def test_the_environment_name_is_the_sorted_request(make_component, make_catalog):
    # `install b a` and `install a b` must name one environment, otherwise the
    # virtualenv, the fingerprint and the lock disagree on its name.
    alpha = make_component("robot-alpha")
    beta = make_component("robot-beta")
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-beta", "robot-alpha"), catalog)

    assert resolution.requested == ("robot-beta", "robot-alpha")
    assert resolution.name == "robot-alpha+robot-beta"


def test_an_empty_request_is_the_minimal_environment(make_catalog):
    resolution = resolve((), make_catalog())

    assert resolution.ok
    assert resolution.name == "minimal"
    assert resolution.components == {}


def test_mutual_requires_is_a_symmetric_closure(make_component, make_catalog):
    # `requires` describes co-installation, which is symmetric; a mutual pair
    # must resolve once per component instead of being rejected as a cycle.
    alpha = make_component("robot-alpha", requires=["robot-beta"])
    beta = make_component("robot-beta", requires=["robot-alpha"])
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha",), catalog)

    assert resolution.ok
    assert sorted(resolution.components) == ["robot-alpha", "robot-beta"]


def test_a_required_component_joins_its_consumers_environment(
    make_component, make_catalog
):
    robot = make_component("robot-alpha", requires=["infra-rlinf"])
    model = make_component("model-molmo", requires=["infra-rlinf"])
    rlinf = make_component("infra-rlinf")
    catalog = _catalog(make_catalog, rlinf, robot, model)

    resolution = resolve(("robot-alpha", "model-molmo"), catalog)

    assert resolution.ok
    # Two consumers in one environment pull the shared runtime in once; it is
    # not a service with an endpoint of its own.
    assert sorted(resolution.components) == [
        "infra-rlinf",
        "model-molmo",
        "robot-alpha",
    ]


def test_an_environment_may_request_a_component_no_robot_requires(
    make_component, make_catalog
):
    # A tool or a simulator installs on its own when a caller names it, even
    # though no robot's requires closure names it.
    flywheel = make_component("tool-flywheel", dependencies=("lerobot", "av"))
    alpha = make_component("robot-alpha")
    catalog = _catalog(make_catalog, flywheel, alpha)

    resolution = resolve(("robot-alpha", "tool-flywheel"), catalog)

    assert resolution.ok
    assert sorted(resolution.components) == ["robot-alpha", "tool-flywheel"]
    assert resolution.components["tool-flywheel"].dependencies == ("lerobot", "av")


def test_unknown_component_is_reported(make_catalog):
    catalog = _catalog(make_catalog)

    resolution = resolve(("robot-missing",), catalog)

    assert not resolution.ok
    assert "references unknown component 'robot-missing'" in resolution.errors[0]


def test_unknown_requires_is_reported(make_component, make_catalog):
    alpha = make_component("robot-alpha", requires=["model-missing"])
    catalog = _catalog(make_catalog, alpha)

    resolution = resolve(("robot-alpha",), catalog)

    assert not resolution.ok
    assert (
        "component 'robot-alpha' requires unknown component 'model-missing'"
        in (resolution.errors[0])
    )


def test_newest_supported_minor_is_chosen(make_component, make_catalog):
    robot = make_component("robot-alpha", python=">=3.10,<3.12")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(("robot-alpha",), catalog)

    assert resolution.ok
    assert resolution.python == "3.11"


def test_unconstrained_components_resolve_to_the_newest_minor(
    make_component, make_catalog
):
    robot = make_component("robot-alpha")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(("robot-alpha",), catalog)

    assert resolution.ok
    assert resolution.python == "3.12"


def test_the_newest_minor_every_component_accepts_wins(make_component, make_catalog):
    robot = make_component("robot-alpha")
    tool = make_component("tool-flywheel", python=">=3.11,<3.12")
    catalog = _catalog(make_catalog, robot, tool)

    resolution = resolve(("robot-alpha", "tool-flywheel"), catalog)

    assert resolution.ok
    assert resolution.python == "3.11"


def test_a_range_the_components_do_not_support_is_reported(
    make_component, make_catalog
):
    robot = make_component("robot-alpha", python=">=3.13")
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(("robot-alpha",), catalog)

    assert not resolution.ok
    assert resolution.python is None
    assert any(
        "no supported Python version" in error and "robot-alpha" in error
        for error in resolution.errors
    )


def test_declared_conflict_in_one_environment_is_reported(make_component, make_catalog):
    alpha = make_component("robot-alpha", env_conflicts=["robot-beta"])
    beta = make_component("robot-beta", env_conflicts=["robot-alpha"])
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha", "robot-beta"), catalog)

    assert not resolution.ok
    assert (
        "places 'robot-alpha' and 'robot-beta' in the same environment"
        in resolution.errors[0]
    )
    assert (
        "split robot-alpha and robot-beta into separate environments and "
        "connect them by endpoint" in resolution.errors[0]
    )


def test_a_conflict_declared_on_one_side_is_enough(make_component, make_catalog):
    # Components no longer have to mirror every conflict in both manifests; one
    # side declaring it keeps the pair apart.
    alpha = make_component("robot-alpha", env_conflicts=["robot-beta"])
    beta = make_component("robot-beta")
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha", "robot-beta"), catalog)

    assert not resolution.ok
    assert "places 'robot-alpha' and 'robot-beta'" in resolution.errors[0]


def test_conflict_reaches_components_pulled_in_by_requires(
    make_component, make_catalog
):
    robot = make_component("robot-alpha", requires=["model-policy"])
    policy = make_component("model-policy", env_conflicts=["model-grounder"])
    grounder = make_component("model-grounder", env_conflicts=["model-policy"])
    catalog = _catalog(make_catalog, robot, policy, grounder)

    resolution = resolve(("robot-alpha", "model-grounder"), catalog)

    assert not resolution.ok
    assert (
        "places 'model-grounder' and 'model-policy' in the same environment"
        in (resolution.errors[0])
    )


def test_declared_conflict_is_allowed_across_separate_environments(
    make_component, make_catalog
):
    alpha = make_component("robot-alpha", env_conflicts=["robot-beta"])
    beta = make_component("robot-beta", env_conflicts=["robot-alpha"])
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(("robot-alpha",), catalog).ok
    assert resolve(("robot-beta",), catalog).ok


def test_two_components_cannot_override_one_package(
    make_component, make_catalog, tmp_path
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("# keep numpy below 2\nnumpy<2\n", encoding="utf-8")
    right.write_text("numpy<3\n", encoding="utf-8")
    alpha = make_component("robot-alpha", overrides=[left])
    beta = make_component("robot-beta", overrides=[right])
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha", "robot-beta"), catalog)

    assert not resolution.ok
    # uv merges the override files, so the winner would depend on file order.
    assert "both override 'numpy'" in resolution.errors[0]
    assert "merge the override files" in resolution.errors[0]


def test_marker_scoped_overrides_leave_the_choice_to_uv(
    make_component, make_catalog, tmp_path
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("numpy<2\n", encoding="utf-8")
    right.write_text('numpy<3; sys_platform == "win32"\n', encoding="utf-8")
    alpha = make_component("robot-alpha", overrides=[left])
    beta = make_component("robot-beta", overrides=[right])
    catalog = _catalog(make_catalog, alpha, beta)

    # The two lines select different targets, so the resolver decides which
    # one applies instead of the check reporting a duplicate.
    assert resolve(("robot-alpha", "robot-beta"), catalog).ok


def test_incompatible_pins_are_reported(make_component, make_catalog):
    alpha = make_component("robot-alpha", dependencies=["torch==2.7.0"])
    beta = make_component("robot-beta", dependencies=["torch==2.8.0"])
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha", "robot-beta"), catalog)

    assert any("conflicting pins for 'torch'" in error for error in resolution.errors)


def test_core_dependencies_join_the_pin_check(make_component, make_catalog):
    alpha = make_component("robot-alpha", dependencies=["torch==2.7.0"])
    catalog = _catalog(make_catalog, alpha)

    resolution = resolve(("robot-alpha",), catalog, core_dependencies=("torch==2.8.0",))

    assert any("conflicting pins for 'torch'" in error for error in resolution.errors)


def test_overlapping_specifiers_are_compatible(make_component, make_catalog):
    alpha = make_component("robot-alpha", dependencies=["huggingface-hub>=0.24,<1"])
    beta = make_component("robot-beta", dependencies=["huggingface-hub>=0.34,<2"])
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(("robot-alpha", "robot-beta"), catalog).ok


def test_range_pins_are_left_to_uv(make_component, make_catalog):
    # `>1.0` and `<1.0.1` overlap at 1.0.post1; sampling boundaries used to
    # report a false conflict, so ranges are not compared statically.
    alpha = make_component("robot-alpha", dependencies=["pkg>1.0"])
    beta = make_component("robot-beta", dependencies=["pkg<1.0.1"])
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(("robot-alpha", "robot-beta"), catalog).ok


def test_marker_scoped_pins_select_one_wheel_and_are_ignored(
    make_component, make_catalog
):
    markers = ' ; python_version == "3.11"'
    alpha = make_component(
        "robot-alpha",
        dependencies=[f"franky @ https://example.test/franky.whl{markers}"],
    )
    beta = make_component(
        "robot-beta",
        dependencies=[f"franky @ https://example.test/franky.whl{markers}"],
    )
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(("robot-alpha", "robot-beta"), catalog).ok


def test_different_url_pins_are_reported(make_component, make_catalog):
    alpha = make_component("robot-alpha", dependencies=["pkg @ https://a.test/pkg.whl"])
    beta = make_component("robot-beta", dependencies=["pkg @ https://b.test/pkg.whl"])
    catalog = _catalog(make_catalog, alpha, beta)

    assert any(
        "conflicting pins for 'pkg'" in error
        for error in resolve(("robot-alpha", "robot-beta"), catalog).errors
    )


def test_manylinux_is_the_newest_baseline_in_the_closure(make_component, make_catalog):
    alpha = make_component("robot-alpha", manylinux="2_35")
    beta = make_component("robot-beta", manylinux="2_31")
    catalog = _catalog(make_catalog, alpha, beta)

    assert resolve(("robot-alpha", "robot-beta"), catalog).manylinux == "2_35"


def test_component_index_settings_are_inherited(make_component, make_catalog):
    robot = make_component(
        "robot-alpha",
        index_url="https://index.test/simple",
        extra_index_urls=("https://extra.test/simple",),
        index_strategy="unsafe-best-match",
    )
    catalog = _catalog(make_catalog, robot)

    resolution = resolve(("robot-alpha",), catalog)

    assert resolution.ok
    assert resolution.index_url == "https://index.test/simple"
    assert resolution.index_strategy == "unsafe-best-match"
    assert resolution.extra_index_urls == ("https://extra.test/simple",)


def test_disagreeing_component_index_settings_are_reported(
    make_component, make_catalog
):
    alpha = make_component("robot-alpha", index_url="https://a.test/simple")
    beta = make_component("robot-beta", index_url="https://b.test/simple")
    catalog = _catalog(make_catalog, alpha, beta)

    resolution = resolve(("robot-alpha", "robot-beta"), catalog)

    assert not resolution.ok
    assert "components declare different index URLs" in resolution.errors[0]
    assert "install these components separately" in resolution.errors[0]
