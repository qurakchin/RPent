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

"""Changed paths narrow CI scope, and anything unrecognised widens it."""

import json

from tests.tooling import affected


def test_paths_map_to_their_component(make_component, make_catalog):
    alpha = make_component("robot-alpha")
    sam3 = make_component("model-sam3")
    catalog = make_catalog(components=[alpha, sam3])

    assert affected.affected_components(["robots/alpha/spec.py"], catalog) == {
        "robot-alpha"
    }
    assert affected.affected_components(
        ["components/models/sam3/server.py"], catalog
    ) == {"model-sam3"}


def test_sim_paths_map_to_their_component(make_component, make_catalog):
    libero = make_component("sim-libero")
    catalog = make_catalog(components=[libero])

    assert affected.affected_components(["components/sim/libero/env.py"], catalog) == {
        "sim-libero"
    }


def test_sim_change_reruns_the_robot_slice_that_wires_it(
    tmp_path, make_component, make_catalog
):
    libero = make_component("sim-libero")
    robot = make_component("robot-libero", requires=("sim-libero",))
    (tmp_path / "tests/unit_tests/robots/libero").mkdir(parents=True)
    (tmp_path / affected.CROSS_COMPONENT_TESTS).mkdir(parents=True)
    catalog = make_catalog(components=[libero, robot])

    scope = affected.affected_scope(
        ["components/sim/libero/env_server.py"], catalog, tmp_path
    )

    assert scope.components == ("sim-libero",)
    # The simulator and the robot environment that requires it both resolve to
    # the changed component, so both are installed.
    assert scope.targets == ("robot-libero", "sim-libero")
    assert "tests/unit_tests/robots/libero" in scope.tests
    assert not scope.full


def test_tool_change_reruns_its_own_tests(tmp_path, make_component, make_catalog):
    flywheel = make_component("tool-flywheel")
    (tmp_path / "tests/unit_tests/components/tools/flywheel").mkdir(parents=True)
    (tmp_path / affected.CROSS_COMPONENT_TESTS).mkdir(parents=True)
    catalog = make_catalog(components=[flywheel])

    scope = affected.affected_scope(
        ["components/tools/flywheel/export.py"], catalog, tmp_path
    )

    assert scope.components == ("tool-flywheel",)
    assert scope.targets == ("tool-flywheel",)
    assert "tests/unit_tests/components/tools/flywheel" in scope.tests
    assert not scope.full


def test_an_unowned_path_means_everything(make_component, make_catalog):
    alpha = make_component("robot-alpha")
    catalog = make_catalog(components=[alpha])

    assert affected.affected_components(["rpent/session/session.py"], catalog) is None
    assert affected.affected_components(["robots/missing/x.py"], catalog) is None


def test_robot_change_narrows_to_its_slice_tests(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    beta = make_component("robot-beta")
    slice_tests = tmp_path / "tests" / "unit_tests" / "robots" / "alpha"
    slice_tests.mkdir(parents=True)
    for shared in affected.ROBOT_SHARED_TESTS:
        (tmp_path / shared).write_text("", encoding="utf-8")
    contracts = tmp_path / affected.CROSS_COMPONENT_TESTS
    contracts.mkdir(parents=True)
    catalog = make_catalog(components=[alpha, beta])

    scope = affected.affected_scope(["robots/alpha/spec.py"], catalog, tmp_path)

    assert scope.components == ("robot-alpha",)
    assert scope.targets == ("robot-alpha",)
    # A component change already narrows to its resolution closure, so a pull
    # request installs exactly the environments a full run would install for it.
    assert scope.pr_targets == ("robot-alpha",)
    assert "tests/unit_tests/robots/alpha" in scope.tests
    assert "tests/unit_tests/robots/test_toolkit_contracts.py" in scope.tests
    # The cross-component contracts cover this slice too, so they rerun.
    assert "tests/unit_tests/contracts" in scope.tests
    assert not scope.full


def test_model_change_reruns_the_cross_component_contracts(
    tmp_path, make_component, make_catalog
):
    sam3 = make_component("model-sam3")
    (tmp_path / affected.CROSS_COMPONENT_TESTS).mkdir(parents=True)
    catalog = make_catalog(components=[sam3])

    scope = affected.affected_scope(
        ["components/models/sam3/platforms.py"], catalog, tmp_path
    )

    assert "tests/unit_tests/contracts" in scope.tests


def test_contract_change_runs_only_the_contract_group(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    catalog = make_catalog(components=[alpha])

    scope = affected.affected_scope(
        ["tests/unit_tests/contracts/test_model_platforms.py"], catalog, tmp_path
    )

    assert scope.tests == ("tests/unit_tests/contracts",)
    assert scope.targets == ()
    assert scope.pr_targets == ()
    assert not scope.full


def test_component_without_tests_runs_the_whole_suite(
    tmp_path, make_component, make_catalog
):
    sam3 = make_component("model-sam3")
    catalog = make_catalog(components=[sam3])

    scope = affected.affected_scope(
        ["components/models/sam3/server.py"], catalog, tmp_path
    )

    assert scope.tests == ("tests/unit_tests",)


def test_docs_only_change_needs_no_tests_or_environments(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    catalog = make_catalog(components=[alpha])

    scope = affected.affected_scope(
        ["README.md", "docs/source-en/index.rst"], catalog, tmp_path
    )

    assert scope.docs
    assert scope.tests == ()
    assert scope.targets == ()
    assert scope.pr_targets == ()
    assert not scope.full


def test_unmapped_path_selects_every_component_and_environment(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    catalog = make_catalog(components=[alpha])

    for path in ("setup.py", "MANIFEST.in"):
        scope = affected.affected_scope([path], catalog, tmp_path)

        assert scope.full
        assert scope.components == ("robot-alpha",)
        assert scope.tests == ("tests/unit_tests",)
        assert scope.targets == ("minimal", "robot-alpha")
        # Packaging decides what every environment installs, so a pull request
        # keeps the full environment set rather than the pilot one.
        assert scope.pr_targets == ("minimal", "robot-alpha")


def test_core_change_installs_the_pilot_environments_in_a_pull_request(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    robotwin = make_component("robot-robotwin")
    unit_cpu = make_component("infra-unit_cpu")
    catalog = make_catalog(components=[alpha, robotwin, unit_cpu])

    for path in ("rpent/session/session.py", "tests/unit_tests/rpent/test_session.py"):
        scope = affected.affected_scope([path], catalog, tmp_path)

        assert scope.full
        assert scope.targets == (
            "minimal",
            "infra-unit_cpu",
            "robot-alpha",
            "robot-robotwin",
        )
        assert scope.pr_targets == (
            "minimal",
            "robot-robotwin",
            "infra-unit_cpu",
        )


def test_installer_change_installs_every_environment_in_a_pull_request(
    tmp_path, make_component, make_catalog
):
    alpha = make_component("robot-alpha")
    catalog = make_catalog(components=[alpha])

    scope = affected.affected_scope(["rpent/install/lock.py"], catalog, tmp_path)

    assert scope.full
    assert scope.tests == ("tests/unit_tests",)
    assert scope.targets == ("minimal", "robot-alpha")
    assert scope.pr_targets == ("minimal", "robot-alpha")


def _install_data_catalog(make_component, make_catalog):
    """Build a catalog with a robot and the shared infra component it requires."""
    shared = make_component(
        "infra-shared",
        dependencies=["packaging"],
    )
    alpha = make_component("robot-alpha", requires=("infra-shared",))
    return make_catalog(components=[alpha, shared])


def test_lock_change_runs_the_contract_tests_for_its_environment(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(["tests/locks/minimal.lock"], catalog, tmp_path)

    assert not scope.full
    assert scope.components == ()
    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.targets == ("minimal",)
    assert scope.pr_targets == ("minimal",)


def test_manifest_change_narrows_to_its_own_environment(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(
        ["components/infra/shared/component.toml"], catalog, tmp_path
    )

    assert scope.components == ()
    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.targets == ("infra-shared",)
    assert not scope.full


def test_a_lock_for_an_unknown_environment_widens_to_all(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(["tests/locks/removed.lock"], catalog, tmp_path)

    assert scope.targets == ("minimal", "infra-shared", "robot-alpha")


def test_packaging_settings_keep_every_environment(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(["pyproject.toml"], catalog, tmp_path)

    assert not scope.full
    assert scope.components == ()
    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.targets == ("minimal", "infra-shared", "robot-alpha")
    assert scope.pr_targets == ("minimal", "infra-shared", "robot-alpha")


def test_repository_contract_test_change_installs_no_environment(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(
        ["tests/unit_tests/installs/test_catalog.py"], catalog, tmp_path
    )

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.targets == ()
    assert scope.pr_targets == ()
    assert not scope.full


def test_unrecognised_install_data_widens_to_every_environment(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(["tests/locks/matrix.toml"], catalog, tmp_path)

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.targets == ("minimal", "infra-shared", "robot-alpha")


def test_mixed_install_and_core_change_widens_to_everything(
    tmp_path, make_component, make_catalog
):
    catalog = _install_data_catalog(make_component, make_catalog)

    scope = affected.affected_scope(
        ["tests/locks/minimal.lock", "rpent/session/session.py"],
        catalog,
        tmp_path,
    )

    assert scope.full
    assert scope.tests == ("tests/unit_tests",)
    assert scope.targets == ("minimal", "infra-shared", "robot-alpha")


def test_main_prints_scope_as_json(tmp_path, write_toml, capsys):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "json"
        """,
    )

    assert affected.main(["robots/alpha/spec.py"], root=tmp_path) == 0

    scope = json.loads(capsys.readouterr().out)
    assert scope["components"] == ["robot-alpha"]
    assert scope["targets"] == ["robot-alpha"]
    assert not scope["full"]


def test_runner_filter_narrows_both_environment_sets(tmp_path, write_toml, capsys):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    write_toml(
        "components/models/molmo/component.toml",
        """
        schema = 2
        name = "model-molmo"
        probe = "json"
        """,
    )
    write_toml(
        "components/infra/unit_cpu/component.toml",
        """
        schema = 2
        name = "infra-unit_cpu"
        probe = "json"
        """,
    )

    assert (
        affected.main(["rpent/session/session.py", "--runner", "gpu"], root=tmp_path)
        == 0
    )

    scope = json.loads(capsys.readouterr().out)
    assert scope["targets"] == ["model-molmo"]
    assert scope["pr_targets"] == []
