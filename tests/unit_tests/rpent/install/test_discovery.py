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


def _manifest(write_toml, relative, name, kind, *, conflicts=(), requires=()):
    rendered = ", ".join(f'"{item}"' for item in conflicts)
    required = ", ".join(f'"{item}"' for item in requires)
    return write_toml(
        f"{relative}/{name}/component.toml",
        f"""
        schema = 2
        name = "{name}"
        kind = "{kind}"
        python = "3.11"
        probe = "{name}"
        requires = [{required}]
        env_conflicts = [{rendered}]
        """,
    )


def test_discovery_loads_components_targets_and_conflict_symmetry(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["beta"])
    _manifest(write_toml, "robots", "beta", "robot", conflicts=["alpha"])
    _manifest(write_toml, "components/models", "sam3", "model")
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"

        [components.alpha]

        [components.beta]
        """,
    )

    catalog = discover(tmp_path)

    assert sorted(catalog.components) == ["alpha", "beta", "sam3"]
    assert catalog.components["sam3"].kind == "model"
    assert "alpha" in catalog.targets["gpu"].components


def test_component_kind_must_match_root(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "model")

    with pytest.raises(InstallConfigError, match="does not match"):
        discover_components(tmp_path)


def test_duplicate_component_names_are_rejected(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    _manifest(write_toml, "components/models", "alpha", "model")

    with pytest.raises(InstallConfigError, match="declared twice"):
        discover_components(tmp_path)


def test_conflicts_must_reference_known_components(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["missing"])

    with pytest.raises(InstallConfigError, match="unknown component"):
        discover_components(tmp_path)


def test_one_sided_conflicts_are_closed_symmetrically(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["beta"])
    _manifest(write_toml, "robots", "beta", "robot")

    components = discover_components(tmp_path)

    assert components["alpha"].env_conflicts == ("beta",)
    assert components["beta"].env_conflicts == ("alpha",)


def test_conflicts_must_not_name_the_component_itself(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["alpha"])

    with pytest.raises(InstallConfigError, match="names the component itself"):
        discover_components(tmp_path)


def test_targets_are_discovered_by_filename(tmp_path, write_toml):
    write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.10"
        """,
    )

    targets = discover_targets(tmp_path)

    assert targets["alpha"].python == "3.10"


def test_a_component_without_a_target_file_is_installable_by_name(tmp_path, write_toml):
    write_toml(
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "model"
        probe = "alpha"
        python = "3.11"
        """,
    )

    targets = discover_targets(tmp_path)

    assert targets["alpha"].python == "3.11"
    assert (
        targets["alpha"].relative_path(tmp_path)
        == "components/models/alpha/component.toml"
    )
    assert list(targets["alpha"].components) == ["alpha"]


def test_a_robot_needs_an_explicit_target(tmp_path, write_toml):
    # Installing a robot means choosing the environment it runs in, which only
    # a target file can declare.
    _manifest(write_toml, "robots", "alpha", "robot")

    assert "alpha" not in discover_targets(tmp_path)


def test_a_robot_override_target_must_select_the_robot(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"

        [components]
        """,
    )

    with pytest.raises(InstallConfigError, match="does not select it"):
        discover_targets(tmp_path)


def test_a_robot_override_target_installs_the_robot_it_names(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"

        [components.alpha]
        """,
    )

    targets = discover_targets(tmp_path)

    assert list(targets["alpha"].components) == ["alpha"]
    assert targets["alpha"].relative_path(tmp_path) == "installs/targets/alpha.toml"


def test_a_target_may_not_reuse_a_non_robot_component_name(tmp_path, write_toml):
    _manifest(write_toml, "components/models", "sam3", "model")
    write_toml(
        "installs/targets/sam3.toml",
        """
        schema = 2
        kind = "target"
        name = "sam3"
        python = "3.11"

        [components.sam3]
        """,
    )

    with pytest.raises(InstallConfigError, match="already installable under"):
        discover_targets(tmp_path)


def test_imports_must_be_declared_in_requires(tmp_path, write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "alpha"
        imports = ["beta"]
        """,
    )
    _manifest(write_toml, "robots", "beta", "robot")

    with pytest.raises(InstallConfigError, match="neither.*requires the other"):
        discover_components(tmp_path)


def test_imports_may_rely_on_the_other_components_requires(tmp_path, write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "alpha"
        imports = ["beta"]
        """,
    )
    _manifest(write_toml, "robots", "beta", "robot", requires=["alpha"])

    components = discover_components(tmp_path)

    assert components["alpha"].imports == ("beta",)


def test_imports_must_name_a_same_kind_component(tmp_path, write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "alpha"
        requires = ["sam3"]
        imports = ["sam3"]
        """,
    )
    _manifest(write_toml, "components/models", "sam3", "model")

    with pytest.raises(InstallConfigError, match="must name a robot component"):
        discover_components(tmp_path)


def test_imports_are_only_allowed_on_robot_slices(tmp_path, write_toml):
    write_toml(
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "model"
        probe = "alpha"
        requires = ["beta"]
        imports = ["beta"]
        """,
    )
    _manifest(write_toml, "components/models", "beta", "model", requires=["alpha"])

    with pytest.raises(InstallConfigError, match="imports is only for robot slices"):
        discover_components(tmp_path)


def test_apple_double_metadata_is_ignored(tmp_path, write_toml):
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.10"
        """,
    )
    # A network filesystem stores macOS extended attributes as ._<name> files.
    (tmp_path / "installs" / "targets" / "._gpu.toml").write_bytes(
        b"\xa3\na metadata file"
    )
    _manifest(write_toml, "robots", "alpha", "robot")
    (tmp_path / "robots" / "._alpha").write_bytes(b"\xa3 metadata")

    assert list(discover_components(tmp_path)) == ["alpha"]
    assert sorted(discover_targets(tmp_path)) == ["gpu"]


def test_a_target_inherits_the_index_settings_its_components_declare(
    tmp_path, write_toml
):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        python = "3.11"
        probe = "alpha"
        manylinux = "2_35"
        index-url = "https://example.invalid/simple"
        extra-index-urls = ["https://example.invalid/extra"]
        index-strategy = "unsafe-best-match"
        """,
    )
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"
        manylinux = "2_35"

        [components.alpha]
        """,
    )

    target = discover_targets(tmp_path)["gpu"]

    assert target.index_url == "https://example.invalid/simple"
    assert target.index_strategy == "unsafe-best-match"
    assert target.extra_index_urls == ("https://example.invalid/extra",)


def test_a_target_keeps_its_own_extra_index_urls_beside_the_inherited_ones(
    tmp_path, write_toml
):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        python = "3.11"
        probe = "alpha"
        extra-index-urls = ["https://example.invalid/alpha"]
        """,
    )
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"
        extra-index-urls = ["https://example.invalid/target"]

        [components.alpha]
        """,
    )

    target = discover_targets(tmp_path)["gpu"]

    assert target.extra_index_urls == (
        "https://example.invalid/alpha",
        "https://example.invalid/target",
    )


def test_components_that_need_different_indexes_cannot_share_an_environment(
    tmp_path, write_toml
):
    write_toml(
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "model"
        python = "3.11"
        probe = "alpha"
        index-strategy = "unsafe-best-match"
        """,
    )
    write_toml(
        "components/models/beta/component.toml",
        """
        schema = 2
        name = "beta"
        kind = "model"
        python = "3.11"
        probe = "beta"
        index-strategy = "unsafe-first-match"
        """,
    )
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"

        [components.alpha]

        [components.beta]
        """,
    )

    with pytest.raises(InstallConfigError, match="different index strategies"):
        discover_targets(tmp_path)


def test_a_target_baseline_must_cover_the_components_it_installs(tmp_path, write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        python = "3.11"
        probe = "alpha"
        manylinux = "2_35"
        """,
    )
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"
        manylinux = "2_31"

        [components.alpha]
        """,
    )

    with pytest.raises(InstallConfigError, match="cannot serve alpha"):
        discover_targets(tmp_path)


def _deps_manifest(write_toml, name):
    return write_toml(
        f"installs/deps/{name}.toml",
        f"""
        schema = 2
        name = "{name}"
        kind = "deps"
        python = "3.11"
        probe = "{name}"
        """,
    )


def test_a_target_may_select_a_deps_component(tmp_path, write_toml):
    _deps_manifest(write_toml, "shared")
    _manifest(write_toml, "robots", "alpha", "robot", requires=["shared"])
    write_toml(
        "installs/targets/gpu.toml",
        """
        schema = 2
        kind = "target"
        name = "gpu"
        python = "3.11"

        [components.alpha]

        [components.shared]
        """,
    )

    targets = discover_targets(tmp_path)

    assert "shared" in targets["gpu"].components


def test_a_deps_component_needs_two_consumers_or_a_target_selection(
    tmp_path, write_toml
):
    _deps_manifest(write_toml, "shared")
    _manifest(write_toml, "robots", "alpha", "robot", requires=["shared"])

    with pytest.raises(InstallConfigError, match="no target selects it"):
        discover_targets(tmp_path)

    _manifest(write_toml, "robots", "beta", "robot", requires=["shared"])

    assert "shared" in discover(tmp_path).components
