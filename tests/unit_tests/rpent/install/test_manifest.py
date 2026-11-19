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

"""Component manifests and environment targets parse into install inputs."""

import pytest

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    load_component,
    load_deps_component,
    load_target,
    python_specifier,
)


def test_component_manifest_reads_declarations(write_toml):
    write_toml("robots/alpha/overrides.txt", "torch==2.7")
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha.robot_spec"
        python = ">=3.11,<3.12"
        requires = ["openpi"]
        env_conflicts = ["beta"]
        dependencies = ["numpy>=2,<3"]
        overrides = ["overrides.txt"]

        [optional]
        pro = ["extra-package"]
        """,
    )

    component = load_component(path)

    assert component.name == "alpha"
    assert component.kind == "robot"
    assert component.python == ">=3.11,<3.12"
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
        schema = 2
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
        schema = 2
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
        schema = 2
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
        schema = 2
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
        schema = 2
        name = "beta"
        kind = "robot"
        probe = "robots.beta"
        """,
    )

    with pytest.raises(InstallConfigError, match="must match its directory"):
        load_component(path)


def test_component_rejects_a_removed_placement_field(write_toml):
    # A service that needs its own environment is installed as its own target
    # and reached by endpoint; a component never sits outside its target.
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        placement = ["in-env"]
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown component field"):
        load_component(path)


def test_git_dependencies_must_pin_a_commit_or_version_tag(write_toml):
    branch = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git@main"]
        """,
    )
    commit = write_toml(
        "robots/beta/component.toml",
        """
        schema = 2
        name = "beta"
        kind = "robot"
        probe = "robots.beta"
        dependencies = [
          "pkg @ git+https://github.com/example/pkg.git@0123456789abcdef0123456789abcdef01234567",
        ]
        """,
    )
    tag = write_toml(
        "robots/gamma/component.toml",
        """
        schema = 2
        name = "gamma"
        kind = "robot"
        probe = "robots.gamma"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git@v1.2.3"]
        """,
    )

    with pytest.raises(InstallConfigError, match="pins git ref 'main'"):
        load_component(branch)
    assert load_component(commit).dependencies[0].endswith("01234567")
    assert load_component(tag).dependencies == (
        "pkg @ git+https://github.com/example/pkg.git@v1.2.3",
    )


def test_target_git_dependencies_must_pin_a_commit_or_version_tag(write_toml):
    path = write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git@main"]
        """,
    )

    with pytest.raises(InstallConfigError, match="pins git ref 'main'"):
        load_target(path)


def test_git_dependency_without_a_ref_is_rejected(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git"]
        """,
    )

    with pytest.raises(InstallConfigError, match="has no git ref"):
        load_component(path)


def test_deps_component_rejects_requires(write_toml):
    path = write_toml(
        "installs/deps/rlinf.toml",
        """
        schema = 2
        name = "rlinf"
        kind = "deps"
        probe = "rlinf"
        requires = ["openpi"]
        """,
    )

    with pytest.raises(InstallConfigError, match="cannot require other components"):
        load_deps_component(path)


def test_component_rejects_an_absolute_override(write_toml):
    override = write_toml("robots/alpha/overrides.txt", "torch==2.7")
    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        overrides = ["{override}"]
        """,
    )

    with pytest.raises(InstallConfigError, match="must be relative to the component"):
        load_component(path)


def test_component_rejects_missing_override(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "robots.alpha"
        overrides = ["missing.txt"]
        """,
    )

    with pytest.raises(InstallConfigError, match="override file not found"):
        load_component(path)


def test_target_reads_components_and_disables_generated_extra(write_toml):
    path = write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.10"
        description = "test target"

        dependencies = ["pytest"]

        [components.alpha]
        variant = "pro"

        [components.beta]
        """,
    )

    target = load_target(path)

    assert target.python == "3.10"
    assert target.components["alpha"].variant == "pro"
    assert target.dependencies == ("pytest",)


def test_target_manylinux_defaults_and_overrides(write_toml):
    default = load_target(
        write_toml(
            "installs/targets/alpha.toml",
            """
            schema = 2
            kind = "target"
            name = "alpha"
            python = "3.11"
            """,
        )
    )
    raised = load_target(
        write_toml(
            "installs/targets/beta.toml",
            """
            schema = 2
            kind = "target"
            name = "beta"
            python = "3.11"
            manylinux = "2_35"
            """,
        )
    )

    assert default.manylinux == "2_31"
    assert raised.manylinux == "2_35"


def test_target_index_strategy_is_optional_and_validated(write_toml):
    default = load_target(
        write_toml(
            "installs/targets/alpha.toml",
            """
            schema = 2
            kind = "target"
            name = "alpha"
            python = "3.11"
            """,
        )
    )
    declared = load_target(
        write_toml(
            "installs/targets/beta.toml",
            """
            schema = 2
            kind = "target"
            name = "beta"
            python = "3.11"
            index-strategy = "unsafe-first-match"
            """,
        )
    )
    invalid = write_toml(
        "installs/targets/gamma.toml",
        """
        schema = 2
        kind = "target"
        name = "gamma"
        python = "3.11"
        index-strategy = "best-match"
        """,
    )

    assert default.index_strategy is None
    assert declared.index_strategy == "unsafe-first-match"
    with pytest.raises(InstallConfigError, match="'index-strategy' must be one of"):
        load_target(invalid)


def test_target_rejects_invalid_manylinux(write_toml):
    path = write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"
        manylinux = "manylinux_2_31"
        """,
    )

    with pytest.raises(InstallConfigError, match="'manylinux' must name a glibc"):
        load_target(path)


@pytest.mark.parametrize(
    ("python", "expected"),
    [
        ("3.11", "==3.11.*"),
        (">=3.10,<3.13", ">=3.10,<3.13"),
    ],
)
def test_target_accepts_a_python_version_or_range_and_normalizes_it(
    write_toml, python, expected
):
    from packaging.specifiers import SpecifierSet

    path = write_toml(
        "installs/targets/alpha.toml",
        f"""
        schema = 2
        kind = "target"
        name = "alpha"
        python = "{python}"
        """,
    )

    assert load_target(path).python == python
    assert python_specifier(python) == SpecifierSet(expected)


def test_target_rejects_an_invalid_python_request(write_toml):
    path = write_toml(
        "installs/targets/alpha.toml",
        """
        schema = 2
        kind = "target"
        name = "alpha"
        python = "three"
        """,
    )

    with pytest.raises(InstallConfigError, match="invalid 'python' request"):
        load_target(path)


@pytest.mark.parametrize(
    "entry",
    [
        '[components.alpha]\nplacement = "in-env"',
        '[components.alpha]\ntarget = "model"',
        "[components.alpha]\ntypo = true",
    ],
)
def test_target_rejects_an_unknown_component_selection_field(write_toml, entry):
    path = write_toml(
        "installs/targets/alpha.toml",
        f"""
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"

        {entry}
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown field"):
        load_target(path)


@pytest.mark.parametrize(
    "field",
    (
        'index_url = "https://example.invalid/simple"',
        # Documentation links and lock paths are not installation settings; a
        # lock is found by target name under tests/locks instead.
        'docs = "docs/source-en/index.rst"',
    ),
)
def test_a_component_rejects_a_top_level_field_it_does_not_define(write_toml, field):
    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "alpha"
        {field}
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown component field"):
        load_component(path)


@pytest.mark.parametrize(
    "field",
    (
        'placements = ["in-env"]',
        'lock = "tests/locks/alpha.lock"',
        'docs = "docs/source-en/index.rst"',
    ),
)
def test_a_target_rejects_a_top_level_field_it_does_not_define(write_toml, field):
    path = write_toml(
        "installs/targets/alpha.toml",
        f"""
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"
        {field}
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown target field"):
        load_target(path)
