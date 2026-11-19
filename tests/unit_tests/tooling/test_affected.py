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
import sys

from rpent.install.fingerprint import runtime_platform
from rpent.install.manifest import Selection
from tests.tooling import affected


def test_paths_map_to_their_component(make_component, make_catalog):
    alpha = make_component("alpha")
    sam3 = make_component("sam3", kind="model", placements=("in-env",))
    catalog = make_catalog(components=[alpha, sam3])

    assert affected.affected_components(["robots/alpha/spec.py"], catalog) == {"alpha"}
    assert affected.affected_components(
        ["components/models/sam3/server.py"], catalog
    ) == {"sam3"}


def test_an_unowned_path_means_everything(make_component, make_catalog):
    alpha = make_component("alpha")
    catalog = make_catalog(components=[alpha])

    assert affected.affected_components(["rpent/session/session.py"], catalog) is None
    assert affected.affected_components(["robots/missing/x.py"], catalog) is None


def test_robot_change_narrows_to_its_slice_tests(
    tmp_path, make_component, make_profile, make_catalog
):
    alpha = make_component("alpha")
    beta = make_component("beta")
    slice_tests = tmp_path / "tests" / "unit_tests" / "robots" / "alpha"
    slice_tests.mkdir(parents=True)
    for shared in affected.ROBOT_SHARED_TESTS:
        (tmp_path / shared).write_text("", encoding="utf-8")
    catalog = make_catalog(
        components=[alpha, beta],
        profiles={
            "alpha": make_profile("alpha", {"alpha": Selection()}),
            "beta": make_profile("beta", {"beta": Selection()}),
        },
    )

    scope = affected.affected_scope(["robots/alpha/spec.py"], catalog, tmp_path)

    assert scope.components == ("alpha",)
    assert scope.profiles == ("alpha",)
    # A component change already narrows to its resolution closure, so a pull
    # request installs exactly the profiles a full run would install for it.
    assert scope.pr_profiles == ("alpha",)
    assert "tests/unit_tests/robots/alpha" in scope.tests
    assert "tests/unit_tests/robots/test_toolkit_contracts.py" in scope.tests
    assert not scope.full


def test_component_without_tests_runs_the_whole_suite(
    tmp_path, make_component, make_profile, make_catalog
):
    sam3 = make_component("sam3", kind="model", placements=("in-env",))
    catalog = make_catalog(
        components=[sam3],
        profiles={"sam3-server": make_profile("sam3-server", {"sam3": Selection()})},
    )

    scope = affected.affected_scope(
        ["components/models/sam3/server.py"], catalog, tmp_path
    )

    assert scope.tests == ("tests/unit_tests",)


def test_docs_only_change_needs_no_tests_or_profiles(
    tmp_path, make_component, make_profile, make_catalog
):
    alpha = make_component("alpha")
    catalog = make_catalog(
        components=[alpha],
        profiles={"alpha": make_profile("alpha", {"alpha": Selection()})},
    )

    scope = affected.affected_scope(
        ["README.md", "docs/source-en/index.rst"], catalog, tmp_path
    )

    assert scope.docs
    assert scope.tests == ()
    assert scope.profiles == ()
    assert scope.pr_profiles == ()
    assert not scope.full


def test_unmapped_path_selects_every_component_and_profile(
    tmp_path, make_component, make_profile, make_catalog
):
    alpha = make_component("alpha")
    catalog = make_catalog(
        components=[alpha],
        profiles={"alpha": make_profile("alpha", {"alpha": Selection()})},
    )

    for path in ("setup.py", "MANIFEST.in"):
        scope = affected.affected_scope([path], catalog, tmp_path)

        assert scope.full
        assert scope.components == ("alpha",)
        assert scope.tests == ("tests/unit_tests",)
        assert scope.profiles == ("alpha",)
        # Packaging decides what every environment installs, so a pull request
        # keeps the full profile set rather than the pilot one.
        assert scope.pr_profiles == ("alpha",)


def test_core_change_installs_the_pilot_profiles_in_a_pull_request(
    tmp_path, make_component, make_profile, make_catalog
):
    alpha = make_component("alpha")
    catalog = make_catalog(
        components=[alpha],
        profiles={
            "alpha": make_profile("alpha", {"alpha": Selection()}),
            "minimal": make_profile("minimal", {}),
            "sim-robotwin": make_profile("sim-robotwin", {}),
            "tool-geometry": make_profile("tool-geometry", {}),
        },
    )

    for path in ("rpent/session/session.py", "tests/unit_tests/rpent/test_session.py"):
        scope = affected.affected_scope([path], catalog, tmp_path)

        assert scope.full
        assert scope.profiles == (
            "alpha",
            "minimal",
            "sim-robotwin",
            "tool-geometry",
        )
        assert scope.pr_profiles == ("minimal", "sim-robotwin", "tool-geometry")


def test_installer_change_installs_every_profile_in_a_pull_request(
    tmp_path, make_component, make_profile, make_catalog
):
    alpha = make_component("alpha")
    catalog = make_catalog(
        components=[alpha],
        profiles={
            "robot-libero_pro": make_profile("robot-libero_pro", {}),
            "tool-geometry": make_profile("tool-geometry", {}),
        },
    )

    scope = affected.affected_scope(["rpent/install/lock.py"], catalog, tmp_path)

    assert scope.full
    assert scope.tests == ("tests/unit_tests",)
    assert scope.pr_profiles == ("robot-libero_pro", "tool-geometry")


def _install_data_catalog(make_component, make_profile, make_catalog):
    """Build a catalog with two profiles and a deps component."""
    shared = make_component(
        "shared",
        kind="deps",
        placements=(),
        default_placement=None,
        dependencies=["packaging"],
    )
    alpha = make_component("alpha", requires=("shared",))
    return make_catalog(
        components=[alpha, shared],
        profiles={
            "alpha": make_profile(
                "alpha",
                {"alpha": Selection()},
                lock="installs/locks/alpha.lock",
            ),
            "minimal": make_profile("minimal", {}),
        },
    )


def test_install_data_change_runs_the_repository_contract_tests(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(
        ["installs/profiles/minimal.toml"], catalog, tmp_path
    )

    assert not scope.full
    assert scope.components == ()
    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ("minimal",)
    assert scope.pr_profiles == ("minimal",)


def test_deps_change_reaches_the_profiles_that_require_it(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(["installs/deps/shared.toml"], catalog, tmp_path)

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ("alpha",)


def test_lock_change_reaches_the_profile_that_reads_it(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(["installs/locks/alpha.lock"], catalog, tmp_path)

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ("alpha",)


def test_packaging_settings_keep_every_profile(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(["pyproject.toml"], catalog, tmp_path)

    assert not scope.full
    assert scope.components == ()
    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ("alpha", "minimal")
    assert scope.pr_profiles == ("alpha", "minimal")


def test_repository_contract_test_change_installs_no_profile(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(
        ["tests/unit_tests/installs/test_catalog.py"], catalog, tmp_path
    )

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ()
    assert scope.pr_profiles == ()
    assert not scope.full


def test_unrecognised_install_data_widens_to_every_profile(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(["installs/matrix.toml"], catalog, tmp_path)

    assert scope.tests == ("tests/unit_tests/installs",)
    assert scope.profiles == ("alpha", "minimal")


def test_mixed_install_and_core_change_widens_to_everything(
    tmp_path, make_component, make_profile, make_catalog
):
    catalog = _install_data_catalog(make_component, make_profile, make_catalog)

    scope = affected.affected_scope(
        ["installs/profiles/minimal.toml", "rpent/session/session.py"],
        catalog,
        tmp_path,
    )

    assert scope.full
    assert scope.tests == ("tests/unit_tests",)
    assert scope.profiles == ("alpha", "minimal")
    assert scope.pr_profiles == ("alpha", "minimal")


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
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "json"
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "installs/profiles/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"

        [components.alpha]
        placement = "in-env"
        """,
    )

    assert affected.main(["robots/alpha/spec.py"], root=tmp_path) == 0

    scope = json.loads(capsys.readouterr().out)
    assert scope["components"] == ["alpha"]
    assert scope["profiles"] == ["alpha"]
    assert not scope["full"]


def test_runner_filter_narrows_both_profile_sets(tmp_path, write_toml, capsys):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    for name in ("minimal", "model-molmo", "tool-geometry"):
        write_toml(
            f"installs/profiles/{name}.toml",
            f"""
            schema = 1
            name = "{name}"
            python = "3.11"
            platform = "linux-x86_64"

            [components]
            """,
        )

    assert (
        affected.main(["rpent/session/session.py", "--runner", "gpu"], root=tmp_path)
        == 0
    )

    scope = json.loads(capsys.readouterr().out)
    assert scope["profiles"] == ["model-molmo"]
    assert scope["pr_profiles"] == []
