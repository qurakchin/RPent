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

"""Profile dependency checks resolve with uv without persisting compiled files."""

import os
import stat
from pathlib import Path

import pytest

from rpent.cli.install import main as env_main
from rpent.install.compile import compile_profile, resolve_profile
from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.manifest import Selection


@pytest.fixture
def repo(tmp_path, write_toml):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = ["packaging"]
        """,
    )
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "json"
        platforms = ["linux-x86_64"]
        dependencies = ["numpy>=2"]
        """,
    )
    write_toml(
        "installs/profiles/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "linux-x86_64"

        [components.alpha]
        placement = "in-env"
        """,
    )
    write_toml(
        "robots/beta/component.toml",
        """
        schema = 1
        name = "beta"
        kind = "robot"
        probe = "json"
        platforms = ["linux-x86_64"]
        """,
    )
    write_toml(
        "installs/profiles/beta.toml",
        """
        schema = 1
        name = "beta"
        python = "3.11"
        platform = "linux-x86_64"
        manylinux = "2_35"

        [components.beta]
        placement = "in-env"
        """,
    )
    return tmp_path


@pytest.fixture
def fake_uv(tmp_path, monkeypatch):
    """A uv stand-in that records the compiled requirements at --output-file."""
    uv = tmp_path / "uv"
    uv.write_text(
        """#!/bin/sh
set -eu
pwd -P >> "$(dirname "$0")/uv-pwd"
printf '%s\\n' "$@" > "$(dirname "$0")/uv-args"
[ "$1 $2" = "pip compile" ]
source=$3
output=
previous=
for argument in "$@"; do
  if [ "$previous" = "--output-file" ]; then
    output=$argument
  fi
  previous=$argument
done
[ -n "$output" ]
cp "$source" "$output"
""",
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("RPENT_UV", str(uv))
    return uv


def test_check_resolves_from_the_checkout(repo, fake_uv, monkeypatch):
    # uv discovers ``[tool.uv]`` from its working directory, so dependencies resolved
    # from a subdirectory would record versions the checkout does not select.
    monkeypatch.chdir(repo / "robots")

    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 0

    assert (repo / "uv-pwd").read_text(encoding="utf-8").splitlines() == [
        str(repo.resolve())
    ]


def test_check_resolves_override_files_against_the_checkout(repo, fake_uv, write_toml):
    # uv resolves relative paths against its working directory, so dependencies
    # resolved from a subdirectory would otherwise miss the override.
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "json"
        platforms = ["linux-x86_64"]
        dependencies = ["numpy>=2"]
        overrides = ["requirements/override.txt"]
        """,
    )
    write_toml("robots/alpha/requirements/override.txt", "numpy<3\n")

    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 0

    arguments = (fake_uv.parent / "uv-args").read_text(encoding="utf-8").splitlines()
    value = arguments[arguments.index("--overrides") + 1]
    assert value == str(repo / "robots/alpha/requirements/override.txt")
    assert os.path.isabs(value)


def test_compile_rejects_an_unknown_platform(
    tmp_path, make_component, make_profile, make_catalog, fake_uv
):
    component = make_component("alpha", platforms=("solaris",))
    profile = make_profile(
        "alpha",
        components={"alpha": Selection(placement="in-env")},
        platform="solaris",
        core=False,
    )
    catalog = make_catalog([component], {"alpha": profile})

    with pytest.raises(InstallError, match="unknown platform 'solaris'"):
        compile_profile(
            profile, catalog, root=tmp_path, uv=str(fake_uv), output=tmp_path / "x"
        )


def test_resolve_profile_cleans_up_compiled_requirements(repo, fake_uv):
    catalog = discover(repo)
    text = resolve_profile(
        catalog.profiles["alpha"], catalog, root=repo, uv=str(fake_uv)
    )

    assert "numpy>=2" in text
    arguments = (fake_uv.parent / "uv-args").read_text().splitlines()
    assert not Path(arguments[arguments.index("--output-file") + 1]).exists()
    assert not Path(arguments[2]).exists()


def test_check_resolve_reports_the_uv_solution(repo, fake_uv, capsys):
    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 0
    assert "profile alpha: ok, uv resolved 2 requirements" in capsys.readouterr().out


def test_check_resolve_reports_a_uv_failure(repo, fake_uv, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise InstallError("no solution for numpy>=9")

    monkeypatch.setattr("rpent.cli.install.resolve_profile", fail)

    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 1
    output = capsys.readouterr().out
    assert "profile alpha: FAIL" in output
    assert "no solution for numpy>=9" in output


def test_check_uses_the_profile_manylinux_baseline(repo, fake_uv):
    assert env_main(["--root", str(repo), "check", "beta", "--resolve"]) == 0

    arguments = (fake_uv.parent / "uv-args").read_text(encoding="utf-8").split()
    assert arguments[arguments.index("--python-platform") + 1] == (
        "x86_64-manylinux_2_35"
    )


def test_check_all_reports_failures_and_continues(repo, fake_uv, write_toml, capsys):
    write_toml(
        "robots/gamma/component.toml",
        """
        schema = 1
        name = "gamma"
        kind = "robot"
        probe = "json"
        platforms = ["solaris"]
        """,
    )
    write_toml(
        "installs/profiles/gamma.toml",
        """
        schema = 1
        name = "gamma"
        python = "3.11"
        platform = "solaris"

        [components.gamma]
        placement = "in-env"
        """,
    )

    assert env_main(["--root", str(repo), "check", "--all", "--resolve"]) == 1

    output = capsys.readouterr().out
    assert "profile gamma: FAIL" in output
    assert "unknown platform 'solaris'" in output
    assert "profile alpha: ok" in output
    assert "profile beta: ok" in output
