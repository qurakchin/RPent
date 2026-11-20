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

from rpent.install.discovery import (
    discover,
    discover_components,
    environment_names,
    requested_components,
)
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


def test_discovery_loads_every_component_root(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["robot-beta"])
    _manifest(write_toml, "robots", "beta", "robot")
    _manifest(write_toml, "components/models", "sam3", "model")
    _manifest(write_toml, "components/sim", "libero", "sim")
    _manifest(write_toml, "components/tools", "flywheel", "tool")
    _manifest(write_toml, "components/infra", "dev", "infra")

    catalog = discover(tmp_path)

    assert sorted(catalog.components) == [
        "infra-dev",
        "model-sam3",
        "robot-alpha",
        "robot-beta",
        "sim-libero",
        "tool-flywheel",
    ]
    assert catalog.components["model-sam3"].kind == "model"
    assert catalog.components["sim-libero"].kind == "sim"


def test_every_environment_name_is_minimal_or_a_component(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    _manifest(write_toml, "components/models", "sam3", "model")

    components = discover_components(tmp_path)

    assert environment_names(components) == ("minimal", "model-sam3", "robot-alpha")


def test_minimal_requests_no_component(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    components = discover_components(tmp_path)

    assert requested_components("minimal", components) == ()
    assert requested_components("robot-alpha", components) == ("robot-alpha",)


def test_a_composition_is_named_by_the_sorted_join(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    _manifest(write_toml, "components/models", "sam3", "model")
    components = discover_components(tmp_path)

    assert requested_components("model-sam3+robot-alpha", components) == (
        "model-sam3",
        "robot-alpha",
    )
    with pytest.raises(InstallConfigError, match="not in canonical order"):
        requested_components("robot-alpha+model-sam3", components)


def test_an_unknown_environment_names_the_known_ones(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    components = discover_components(tmp_path)

    with pytest.raises(InstallConfigError, match="unknown environment 'shared'"):
        requested_components("shared", components)


def test_component_name_must_match_its_root_and_directory(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "model")

    with pytest.raises(InstallConfigError, match="must be 'robot-alpha'"):
        discover_components(tmp_path)


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
    _manifest(write_toml, "robots", "alpha", "robot")
    # A network filesystem stores macOS extended attributes as ._<name> files.
    (tmp_path / "components" / "models").mkdir(parents=True, exist_ok=True)
    (tmp_path / "components" / "models" / "._sam3").mkdir()
    (tmp_path / "robots" / "._alpha").write_bytes(b"\xa3 metadata")

    assert sorted(discover_components(tmp_path)) == ["robot-alpha"]


def test_a_component_keeps_its_index_settings(tmp_path, write_toml):
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

    component = discover_components(tmp_path)["model-alpha"]

    assert component.index_url == "https://example.invalid/simple"
    assert component.index_strategy == "unsafe-best-match"
    assert component.extra_index_urls == ("https://example.invalid/extra",)
