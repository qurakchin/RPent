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

"""Component manifests parse into install inputs."""

import pytest

from rpent.install.errors import InstallConfigError
from rpent.install.manifest import (
    MINIMAL_ENVIRONMENT,
    environment_name,
    load_component,
    python_specifier,
)


def test_component_manifest_reads_declarations(write_toml):
    write_toml("robots/alpha/overrides.txt", "torch==2.7")
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha.robot_spec"
        python = ">=3.11,<3.12"
        requires = ["model-openpi"]
        imports = ["robot-beta"]
        env_conflicts = ["sim-robotwin"]
        dependencies = ["numpy>=2,<3"]
        overrides = ["overrides.txt"]
        """,
    )

    component = load_component(path, "robot")

    assert component.name == "robot-alpha"
    assert component.kind == "robot"
    assert component.python == ">=3.11,<3.12"
    assert component.requires == ("model-openpi",)
    assert component.imports == ("robot-beta",)
    assert component.env_conflicts == ("sim-robotwin",)
    assert component.overrides == (path.parent / "overrides.txt",)
    assert component.manylinux == "2_31"


def test_environment_name_sorts_and_deduplicates_the_request():
    assert environment_name(["b", "a", "b"]) == "a+b"
    assert environment_name(["robot-libero"]) == "robot-libero"


def test_an_empty_request_names_the_minimal_environment():
    assert environment_name([]) == MINIMAL_ENVIRONMENT == "minimal"


def test_component_name_must_match_its_kind_and_directory(write_toml):
    wrong_name = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        probe = "robots.alpha"
        """,
    )
    wrong_kind = write_toml(
        "components/sim/alpha/component.toml",
        """
        schema = 2
        name = "sim-beta"
        probe = "components.sim.beta"
        """,
    )

    with pytest.raises(InstallConfigError, match="must be 'robot-alpha'"):
        load_component(wrong_name, "robot")
    with pytest.raises(InstallConfigError, match="must be 'sim-alpha'"):
        load_component(wrong_kind, "sim")


def test_component_kind_must_be_a_known_root(write_toml):
    path = write_toml(
        "components/deps/rlinf/component.toml",
        """
        schema = 2
        name = "deps-rlinf"
        probe = "rlinf"
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown component kind 'deps'"):
        load_component(path, "deps")


@pytest.mark.parametrize(
    "entry",
    (
        'kind = "robot"',
        'variant = "standard"',
        "variant_required = true",
        'platforms = ["windows-x86_64"]',
        "core = false",
        'placement = ["in-env"]',
        'docs = "docs/source-en/index.rst"',
    ),
)
def test_a_component_rejects_a_top_level_field_it_does_not_define(write_toml, entry):
    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        {entry}
        """,
    )

    with pytest.raises(InstallConfigError, match="unknown component field"):
        load_component(path, "robot")


def test_component_python_request_is_validated(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        python = "three"
        """,
    )

    with pytest.raises(InstallConfigError, match="invalid 'python' request"):
        load_component(path, "robot")


def test_component_manylinux_is_validated(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        manylinux = "manylinux_2_31"
        """,
    )

    with pytest.raises(InstallConfigError, match="'manylinux' must name a glibc"):
        load_component(path, "robot")


def test_component_index_strategy_is_optional_and_validated(write_toml):
    default = load_component(
        write_toml(
            "robots/alpha/component.toml",
            """
            schema = 2
            name = "robot-alpha"
            probe = "robots.alpha"
            """,
        ),
        "robot",
    )
    declared = load_component(
        write_toml(
            "robots/beta/component.toml",
            """
            schema = 2
            name = "robot-beta"
            probe = "robots.beta"
            index-url = "https://index.test/simple"
            index-strategy = "unsafe-first-match"
            """,
        ),
        "robot",
    )
    invalid = write_toml(
        "robots/gamma/component.toml",
        """
        schema = 2
        name = "robot-gamma"
        probe = "robots.gamma"
        index-strategy = "best-match"
        """,
    )

    assert default.index_strategy is None
    assert default.index_url is None
    assert declared.index_strategy == "unsafe-first-match"
    assert declared.index_url == "https://index.test/simple"
    with pytest.raises(InstallConfigError, match="'index-strategy' must be one of"):
        load_component(invalid, "robot")


def test_git_dependencies_must_pin_a_commit_or_version_tag(write_toml):
    branch = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git@main"]
        """,
    )
    commit = write_toml(
        "robots/beta/component.toml",
        """
        schema = 2
        name = "robot-beta"
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
        name = "robot-gamma"
        probe = "robots.gamma"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git@v1.2.3"]
        """,
    )

    with pytest.raises(InstallConfigError, match="pins git ref 'main'"):
        load_component(branch, "robot")
    assert load_component(commit, "robot").dependencies[0].endswith("01234567")
    assert load_component(tag, "robot").dependencies == (
        "pkg @ git+https://github.com/example/pkg.git@v1.2.3",
    )


def test_git_dependency_without_a_ref_is_rejected(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        dependencies = ["pkg @ git+https://github.com/example/pkg.git"]
        """,
    )

    with pytest.raises(InstallConfigError, match="has no git ref"):
        load_component(path, "robot")


def test_component_rejects_an_absolute_override(write_toml):
    override = write_toml("robots/alpha/overrides.txt", "torch==2.7")
    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        overrides = ["{override}"]
        """,
    )

    with pytest.raises(InstallConfigError, match="must be relative to the component"):
        load_component(path, "robot")


def test_component_rejects_missing_override(write_toml):
    path = write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        overrides = ["missing.txt"]
        """,
    )

    with pytest.raises(InstallConfigError, match="override file not found"):
        load_component(path, "robot")


@pytest.mark.parametrize(
    ("python", "expected"),
    [
        ("3.11", "==3.11.*"),
        (">=3.10,<3.13", ">=3.10,<3.13"),
    ],
)
def test_component_accepts_a_python_version_or_range_and_normalizes_it(
    write_toml, python, expected
):
    from packaging.specifiers import SpecifierSet

    path = write_toml(
        "robots/alpha/component.toml",
        f"""
        schema = 2
        name = "robot-alpha"
        probe = "robots.alpha"
        python = "{python}"
        """,
    )

    assert load_component(path, "robot").python == python
    assert python_specifier(python) == SpecifierSet(expected)
