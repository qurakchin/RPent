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

"""Component manifests and environment profiles parse into install inputs."""

import pytest

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import load_component, load_profile


def test_component_manifest_reads_declarations(write_toml):
    write_toml("robots/alpha/overrides.txt", "torch==2.7")
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha.robot_spec"
        python = ">=3.11,<3.12"
        platforms = ["linux-x86_64"]
        requires = ["openpi"]
        env_conflicts = ["beta"]
        placement = ["in-env", "external-env"]
        default_placement = "external-env"
        dependencies = ["numpy>=2,<3"]
        overrides = ["overrides.txt"]
        docs = "docs/alpha.rst"

        [optional]
        pro = ["extra-package"]
        """,
    )

    component = load_component(path)

    assert component.name == "alpha"
    assert component.kind == "robot"
    assert component.python == ">=3.11,<3.12"
    assert component.placements == ("in-env", "external-env")
    assert component.default_placement == "external-env"
    assert component.requires == ("openpi",)
    assert component.env_conflicts == ("beta",)
    assert component.overrides == (path.parent / "overrides.txt",)
    assert component.dependencies_for("pro") == (
        "numpy>=2,<3",
        "extra-package",
    )
    with pytest.raises(InstallConfigError, match="unknown variant"):
        component.dependencies_for("missing")


def test_component_declares_a_default_variant(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        variant = "standard"

        [optional]
        standard = ["standard-dep"]
        pro = ["pro-dep"]
        """,
    )

    component = load_component(path)

    assert component.default_variant == "standard"
    assert not component.variant_required


def test_component_rejects_a_required_variant_with_a_default(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        variant = "standard"
        variant_required = true

        [optional]
        standard = ["standard-dep"]
        """,
    )

    with pytest.raises(
        InstallConfigError, match="cannot be combined with a default 'variant'"
    ):
        load_component(path)


def test_component_rejects_unknown_default_variant_and_empty_requirement(
    write_toml,
):
    unknown = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        variant = "missing"

        [optional]
        standard = ["standard-dep"]
        """,
    )
    empty = write_toml(
        "robots/beta/component.toml",
        """
        schema = 1
        name = "beta"
        kind = "robot"
        probe = "robots.beta"
        variant_required = true
        """,
    )

    with pytest.raises(InstallConfigError, match="'variant' 'missing'"):
        load_component(unknown)
    with pytest.raises(InstallConfigError, match="no \\[optional\\] groups"):
        load_component(empty)


def test_component_name_must_match_directory(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "beta"
        kind = "robot"
        probe = "robots.beta"
        """,
    )

    with pytest.raises(InstallConfigError, match="must match its directory"):
        load_component(path)


@pytest.mark.parametrize(
    ("placement", "message"),
    [
        (["bogus"], "unknown placement"),
        (["external-env"], "default_placement"),
    ],
)
def test_component_rejects_invalid_placements(write_toml, placement, message):
    rendered = ", ".join(f'"{item}"' for item in placement)
    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        placement = [{rendered}]
        default_placement = "in-env"
        """,
    )

    with pytest.raises(InstallConfigError, match=message):
        load_component(path)


def test_component_rejects_missing_override(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        overrides = ["missing.txt"]
        """,
    )

    with pytest.raises(InstallConfigError, match="override file not found"):
        load_component(path)


def test_profile_reads_components_and_disables_generated_extra(write_toml):
    path = write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.10"
        platform = "linux-x86_64"
        extra = false
        description = "test profile"

        dependencies = ["pytest"]

        [components.alpha]
        placement = "external-env"
        env = "alpha-model"
        variant = "pro"

        [components.beta]
        placement = "in-env"
        """,
    )

    profile = load_profile(path)

    assert profile.python == "3.10"
    assert profile.generate_extra is False
    assert profile.extra is None
    assert profile.components["alpha"].env == "alpha-model"
    assert profile.components["alpha"].variant == "pro"
    assert profile.dependencies == ("pytest",)


def test_profile_manylinux_defaults_and_overrides(write_toml):
    default = load_profile(
        write_toml(
            "envs/alpha.toml",
            """
            schema = 1
            name = "alpha"
            python = "3.11"
            platform = "linux-x86_64"
            """,
        )
    )
    raised = load_profile(
        write_toml(
            "envs/beta.toml",
            """
            schema = 1
            name = "beta"
            python = "3.11"
            platform = "linux-x86_64"
            manylinux = "2_35"
            """,
        )
    )

    assert default.manylinux == "2_31"
    assert raised.manylinux == "2_35"


def test_profile_rejects_invalid_manylinux(write_toml):
    path = write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "linux-x86_64"
        manylinux = "manylinux_2_31"
        """,
    )

    with pytest.raises(InstallConfigError, match="'manylinux' must name a glibc"):
        load_profile(path)


def test_profile_requires_minor_python(write_toml):
    path = write_toml(
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = ">=3.11"
        platform = "linux-x86_64"
        """,
    )

    with pytest.raises(InstallConfigError, match="pin a minor version"):
        load_profile(path)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ('[components.alpha]\nplacement = "external-env"', "without an 'env' name"),
        (
            '[components.alpha]\nplacement = "in-env"\nenv = "model"',
            "remove 'env'",
        ),
        ("[components.alpha]\ntypo = true", "unknown field"),
    ],
)
def test_profile_rejects_inconsistent_placements(write_toml, entry, message):
    path = write_toml(
        "envs/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "linux-x86_64"

        {entry}
        """,
    )

    with pytest.raises(InstallConfigError, match=message):
        load_profile(path)
