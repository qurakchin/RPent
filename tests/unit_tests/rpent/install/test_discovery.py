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

from rpent.install.discovery import discover, discover_components, discover_profiles
from rpent.install.errors import InstallConfigError


def _manifest(write_toml, relative, name, kind, *, conflicts=(), requires=()):
    rendered = ", ".join(f'"{item}"' for item in conflicts)
    required = ", ".join(f'"{item}"' for item in requires)
    return write_toml(
        f"{relative}/{name}/component.toml",
        f"""
        schema = 1
        name = "{name}"
        kind = "{kind}"
        probe = "{name}"
        requires = [{required}]
        env_conflicts = [{rendered}]
        """,
    )


def test_discovery_loads_components_profiles_and_conflict_symmetry(
    tmp_path, write_toml
):
    _manifest(write_toml, "robots", "alpha", "robot", conflicts=["beta"])
    _manifest(write_toml, "robots", "beta", "robot", conflicts=["alpha"])
    _manifest(write_toml, "capabilities", "sam3", "capability")
    write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "linux-x86_64"

        [components.alpha]
        placement = "in-env"
        """,
    )

    catalog = discover(tmp_path)

    assert sorted(catalog.components) == ["alpha", "beta", "sam3"]
    assert catalog.components["sam3"].kind == "capability"
    assert catalog.profiles["alpha"].components["alpha"].placement == "in-env"


def test_component_kind_must_match_root(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "capability")

    with pytest.raises(InstallConfigError, match="does not match"):
        discover_components(tmp_path)


def test_duplicate_component_names_are_rejected(tmp_path, write_toml):
    _manifest(write_toml, "robots", "alpha", "robot")
    _manifest(write_toml, "toolkits", "alpha", "toolkit")

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


def test_profiles_are_discovered_by_filename(tmp_path, write_toml):
    write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.10"
        platform = "linux-x86_64"
        """,
    )

    profiles = discover_profiles(tmp_path)

    assert profiles["alpha"].python == "3.10"


def test_profiles_require_a_source_checkout(tmp_path):
    with pytest.raises(InstallConfigError, match="envs.*does not exist"):
        discover_profiles(tmp_path)


def test_imports_must_be_declared_in_requires(tmp_path, write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
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
        schema = 1
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
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "alpha"
        requires = ["sam3"]
        imports = ["sam3"]
        """,
    )
    _manifest(write_toml, "capabilities", "sam3", "capability")

    with pytest.raises(InstallConfigError, match="must name a robot component"):
        discover_components(tmp_path)


def test_apple_double_metadata_is_ignored(tmp_path, write_toml):
    write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.10"
        platform = "linux-x86_64"
        """,
    )
    # A network filesystem stores macOS extended attributes as ._<name> files.
    (tmp_path / "envs" / "._alpha.toml").write_bytes(b"\xa3\na metadata file")
    _manifest(write_toml, "robots", "alpha", "robot")
    (tmp_path / "robots" / "._alpha").write_bytes(b"\xa3 metadata")

    assert list(discover_components(tmp_path)) == ["alpha"]
    assert list(discover_profiles(tmp_path)) == ["alpha"]
