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

"""Profile locks are compiled to the declared path and checked for drift."""

import stat

import pytest

from rpent.cli.env import main as env_main
from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.lock import (
    compile_profile,
    lock_path,
    lock_profiles,
    resolve_profile,
)
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
        "envs/alpha.toml",
        """
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "linux-x86_64"
        lock = "envs/locks/alpha.lock"

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
        "envs/beta.toml",
        """
        schema = 1
        name = "beta"
        python = "3.11"
        platform = "linux-x86_64"
        manylinux = "2_35"
        lock = "envs/locks/beta.lock"

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


def test_lock_path_uses_declaration_or_convention(make_profile, tmp_path):
    declared = make_profile("alpha", lock="custom/alpha.lock")
    conventional = make_profile("beta")

    assert lock_path(tmp_path, declared) == tmp_path / "custom/alpha.lock"
    assert lock_path(tmp_path, conventional) == tmp_path / "envs/locks/beta.lock"


def test_lock_writes_the_resolved_requirements(repo, fake_uv):
    assert lock_profiles(["alpha"], root=repo) == 0

    lock = repo / "envs/locks/alpha.lock"
    text = lock.read_text(encoding="utf-8")
    assert "packaging" in text
    assert "numpy>=2" in text


def test_lock_never_compiles_into_the_previous_lock_file(repo, fake_uv):
    # uv seeds resolution from an existing --output-file, so compiling straight
    # into the tracked lock can keep versions the current index no longer
    # selects and leave `--check` disagreeing with `lock`.
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("packaging==0.0.0\n", encoding="utf-8")

    assert lock_profiles(["alpha"], root=repo) == 0

    arguments = (fake_uv.parent / "uv-args").read_text(encoding="utf-8").splitlines()
    output = arguments[arguments.index("--output-file") + 1]
    assert output != str(lock)
    assert "numpy>=2" in lock.read_text(encoding="utf-8")


def test_check_passes_for_an_unchanged_lock(repo, fake_uv, capsys):
    lock_profiles(["alpha"], root=repo)
    capsys.readouterr()

    assert lock_profiles(["alpha"], root=repo, check=True) == 0
    assert "lock ok: alpha" in capsys.readouterr().out


def test_check_reports_a_stale_lock(repo, fake_uv, capsys):
    lock_profiles(["alpha"], root=repo)
    (repo / "envs/locks/alpha.lock").write_text("stale\n", encoding="utf-8")
    capsys.readouterr()

    assert lock_profiles(["alpha"], root=repo, check=True) == 1
    output = capsys.readouterr().out
    assert "lock is out of date for alpha" in output
    assert "stale" in output


def test_check_reports_a_missing_lock(repo, fake_uv, capsys):
    assert lock_profiles(["alpha"], root=repo, check=True) == 1
    assert "missing lock: envs/locks/alpha.lock" in capsys.readouterr().out


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


def test_resolve_profile_compiles_without_writing_a_lock(repo, fake_uv):
    catalog = discover(repo)
    text = resolve_profile(
        catalog.profiles["alpha"], catalog, root=repo, uv=str(fake_uv)
    )

    assert "numpy>=2" in text
    assert not (repo / "envs/locks/alpha.lock").exists()


def test_check_resolve_reports_the_uv_solution(repo, fake_uv, write_toml, capsys):
    write_toml("envs/locks/alpha.lock", "packaging==24.0\nnumpy==2.0.0")

    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 0
    assert "profile alpha: ok, uv resolved 2 requirements" in capsys.readouterr().out


def test_check_resolve_reports_a_uv_failure(
    repo, fake_uv, write_toml, monkeypatch, capsys
):
    write_toml("envs/locks/alpha.lock", "packaging==24.0\nnumpy==2.0.0")

    def fail(*args, **kwargs):
        raise InstallError("no solution for numpy>=9")

    monkeypatch.setattr("rpent.cli.env.resolve_profile", fail)

    assert env_main(["--root", str(repo), "check", "alpha", "--resolve"]) == 1
    output = capsys.readouterr().out
    assert "profile alpha: FAIL" in output
    assert "no solution for numpy>=9" in output


def test_lock_uses_the_profile_manylinux_baseline(repo, fake_uv):
    lock_profiles(["beta"], root=repo)

    arguments = (fake_uv.parent / "uv-args").read_text(encoding="utf-8").split()
    assert arguments[arguments.index("--python-platform") + 1] == (
        "x86_64-manylinux_2_35"
    )


def test_lock_all_reports_failures_and_continues(repo, fake_uv, write_toml, capsys):
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
        "envs/gamma.toml",
        """
        schema = 1
        name = "gamma"
        python = "3.11"
        platform = "solaris"
        lock = "envs/locks/gamma.lock"

        [components.gamma]
        placement = "in-env"
        """,
    )

    assert lock_profiles([], root=repo) == 1

    output = capsys.readouterr().out
    assert "lock gamma: FAIL" in output
    assert "unknown platform 'solaris'" in output
    assert (repo / "envs/locks/alpha.lock").is_file()


def test_lock_all_covers_declared_profiles(repo, fake_uv):
    assert discover(repo).profiles["alpha"].lock == "envs/locks/alpha.lock"

    assert lock_profiles([], root=repo) == 0
    assert (repo / "envs/locks/alpha.lock").is_file()
    assert (repo / "envs/locks/beta.lock").is_file()
