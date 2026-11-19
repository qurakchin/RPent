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

"""Discovery finds every component root and rejects inconsistent declarations."""

import pytest

from rpent.install.discovery import discover, discover_components, discover_targets
from rpent.install.errors import InstallConfigError


def _manifest(
    write_toml,
    relative,
    directory,
    kind,
    *,
    conflicts=(),
    requires=(),
    imports=(),
    extra="",
):
    rendered = ", ".join(f'"{item}"' for item in conflicts)
    required = ", ".join(f'"{item}"' for item in requires)
    imported = ", ".join(f'"{item}"' for item in imports)
    return write_toml(
        f"{relative}/{directory}/component.toml",
        f"""
        schema = 2
        name = "{kind}-{directory}"
        probe = "{kind}_{directory}"
        requires = [{required}]
        imports = [{imported}]
        env_conflicts = [{rendered}]
        {extra}
        """,
    )


def test_discovery_loads_components_and_targets(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["robot-beta"])
    _manifest(write_toml, "robots", "beta", "robot")
    _manifest(write_toml, "components/models", "sam3", "model")
    write_toml(
        "installs/targets/robot-alpha.toml",
        """
        schema = 2
        name = "robot-alpha"

        [components.robot-alpha]

        [components.robot-beta]
        """,
    )

    catalog = discover(tmp_path)

    assert sorted(catalog.components) == [
        "model-sam3",
        "robot-alpha",
        "robot-beta",
    ]
    assert catalog.components["model-sam3"].kind == "model"
    assert "robot-alpha" in catalog.targets["robot-alpha"].components


def test_component_name_must_match_its_root_and_directory(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "model")

    with pytest.raises(InstallConfigError, match="must be 'robot-alpha'"):
        discover_components(tmp_path)


def test_a_target_declared_twice_is_rejected(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    write_toml(
        "installs/targets/shared.toml",
        """
        schema = 2
        name = "shared"
        """,
    )
    write_toml(
        "tests/targets/shared.toml",
        """
        schema = 2
        name = "shared"
        """,
    )

    with pytest.raises(InstallConfigError, match="declared twice"):
        discover_targets(tmp_path)


def test_conflicts_must_reference_known_components(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["robot-missing"])

    with pytest.raises(InstallConfigError, match="unknown component"):
        discover_components(tmp_path)


def test_one_sided_conflicts_are_kept_as_declared(tmp_path, write_toml):
    # Resolution reads the conflict from either side, so the other manifest
    # needs no mirror entry and discovery does not rewrite it.
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["robot-beta"])
    _manifest(write_toml, "robots", "beta", "robot")

    components = discover_components(tmp_path)

    assert components["robot-alpha"].env_conflicts == ("robot-beta",)
    assert components["robot-beta"].env_conflicts == ()


def test_conflicts_must_not_name_the_component_itself(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["robot-alpha"])

    with pytest.raises(InstallConfigError, match="names the component itself"):
        discover_components(tmp_path)


def test_targets_are_discovered_by_filename(tmp_path, write_toml):
    write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        name = "alpha"
        """,
    )

    targets = discover_targets(tmp_path)

    assert targets["alpha"].components == ()


def test_a_non_robot_component_installs_under_its_own_name(tmp_path, write_toml):
    _manifest(write_toml, "components/models", "alpha", "model")

    targets = discover_targets(tmp_path)

    assert targets["model-alpha"].components == ("model-alpha",)
    assert (
        targets["model-alpha"].relative_path(tmp_path)
        == "components/models/alpha/component.toml"
    )


def test_a_sim_component_installs_under_its_own_name(tmp_path, write_toml):
    _manifest(write_toml, "components/sim", "libero", "sim")

    targets = discover_targets(tmp_path)

    assert targets["sim-libero"].components == ("sim-libero",)


def test_a_robot_needs_an_explicit_target(tmp_path, write_toml):
    # Installing a robot means choosing the environment it runs in, which only
    # a target file can declare.
    _manifest(write_toml, "robots", "alpha", "robot")

    assert "robot-alpha" not in discover_targets(tmp_path)


def test_a_robot_override_target_must_select_the_robot(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    write_toml(
        "installs/targets/robot-alpha.toml",
        """
        schema = 2
        name = "robot-alpha"

        [components]
        """,
    )

    with pytest.raises(InstallConfigError, match="does not select it"):
        discover_targets(tmp_path)


def test_a_robot_override_target_installs_the_robot_it_names(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    write_toml(
        "installs/targets/robot-alpha.toml",
        """
        schema = 2
        name = "robot-alpha"

        [components.robot-alpha]
        """,
    )

    targets = discover_targets(tmp_path)

    assert targets["robot-alpha"].components == ("robot-alpha",)
    assert (
        targets["robot-alpha"].relative_path(tmp_path)
        == "installs/targets/robot-alpha.toml"
    )


def test_a_target_may_not_reuse_a_non_robot_component_name(tmp_path, write_toml):
    _manifest(write_toml, "components/models", "sam3", "model")
    write_toml(
        "installs/targets/model-sam3.toml",
        """
        schema = 2
        name = "model-sam3"

        [components.model-sam3]
        """,
    )

    with pytest.raises(InstallConfigError, match="already installable under"):
        discover_targets(tmp_path)


def test_imports_must_be_declared_in_requires(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", imports=["robot-beta"])
    _manifest(write_toml, "robots", "beta", "robot")

    with pytest.raises(InstallConfigError, match="neither.*requires the other"):
        discover_components(tmp_path)


def test_imports_may_rely_on_the_other_components_requires(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", imports=["robot-beta"])
    _manifest(write_toml, "robots", "beta", "robot", requires=["robot-alpha"])

    components = discover_components(tmp_path)

    assert components["robot-alpha"].imports == ("robot-beta",)


def test_imports_must_name_a_same_kind_component(tmp_path, write_toml):
    _manifest(
        write_toml,
        "robots",
        "alpha",
        "robot",
        requires=["model-sam3"],
        imports=["model-sam3"],
    )
    _manifest(write_toml, "components/models", "sam3", "model")

    with pytest.raises(InstallConfigError, match="must name a robot component"):
        discover_components(tmp_path)


def test_imports_are_only_allowed_on_robot_slices(tmp_path, write_toml):
    _manifest(
        write_toml,
        "components/models",
        "alpha",
        "model",
        imports=["model-beta"],
    )
    _manifest(write_toml, "components/models", "beta", "model")

    with pytest.raises(InstallConfigError, match="imports is only for robot slices"):
        discover_components(tmp_path)


def test_a_model_cannot_require_a_simulator(tmp_path, write_toml):
    _manifest(write_toml, "components/models", "alpha", "model", requires=["sim-beta"])
    _manifest(write_toml, "components/sim", "beta", "sim")

    with pytest.raises(InstallConfigError, match="a model component may require only"):
        discover_components(tmp_path)


def test_a_simulator_cannot_require_a_model(tmp_path, write_toml):
    _manifest(write_toml, "components/sim", "alpha", "sim", requires=["model-beta"])
    _manifest(write_toml, "components/models", "beta", "model")

    with pytest.raises(InstallConfigError, match="a sim component may require only"):
        discover_components(tmp_path)


def test_only_a_robot_requires_a_simulator_and_a_model(tmp_path, write_toml):
    _manifest(
        write_toml,
        "robots",
        "alpha",
        "robot",
        requires=["sim-beta", "model-gamma"],
    )
    _manifest(write_toml, "components/sim", "beta", "sim")
    _manifest(write_toml, "components/models", "gamma", "model")

    components = discover_components(tmp_path)

    assert components["robot-alpha"].requires == ("sim-beta", "model-gamma")


def test_requires_must_name_a_known_component(tmp_path, write_toml):
    _manifest(write_toml, "components/sim", "alpha", "sim", requires=["infra-missing"])

    with pytest.raises(InstallConfigError, match="requires unknown component"):
        discover_components(tmp_path)


def test_apple_double_metadata_is_ignored(tmp_path, write_toml):
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        name = "gpu"
        """,
    )
    # A network filesystem stores macOS extended attributes as ._<name> files.
    (tmp_path / "installs" / "targets" / "._gpu.toml").write_bytes(
        b"\xa3\na metadata file"
    )
    _manifest(write_toml, "robots", "alpha", "robot")
    (tmp_path / "robots" / "._alpha").write_bytes(b"\xa3 metadata")

    assert list(discover_components(tmp_path)) == ["robot-alpha"]
    assert sorted(discover_targets(tmp_path)) == ["gpu"]


def test_a_component_target_keeps_the_component_index_settings(tmp_path, write_toml):
    _manifest(
        write_toml,
        "components/models",
        "alpha",
        "model",
        extra="""
        index-url = "https://example.invalid/simple"
        extra-index-urls = ["https://example.invalid/extra"]
        index-strategy = "unsafe-best-match"
        """,
    )

    target = discover_targets(tmp_path)["model-alpha"]

    assert target.index_url == "https://example.invalid/simple"
    assert target.index_strategy == "unsafe-best-match"
    assert target.extra_index_urls == ("https://example.invalid/extra",)


def test_an_infra_component_installs_under_its_own_name(tmp_path, write_toml):
    _manifest(write_toml, "components/infra", "rlinf", "infra")
    _manifest(
        write_toml, "robots", "alpha", "robot", requires=["infra-rlinf"]
    )

    assert "infra-rlinf" in discover(tmp_path).components
    assert discover(tmp_path).targets["infra-rlinf"].components == ("infra-rlinf",)
