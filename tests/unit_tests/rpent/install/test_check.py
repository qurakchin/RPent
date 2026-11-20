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

"""``rpent-install check`` reports broken environments without installing."""

from rpent.install import check
from rpent.install.discovery import discover


def _write_component(write_toml, name="alpha", dependencies=("alpha-dep",)):
    rendered = ", ".join(f'"{dependency}"' for dependency in dependencies)
    write_toml(
        f"robots/{name}/component.toml",
        f"""
        schema = 2
        name = "robot-{name}"
        probe = "json"
        dependencies = [{rendered}]
        """,
    )


def _write_pyproject(write_toml):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )


def test_a_valid_environment_reports_what_it_installs(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml)

    assert check.main(["robot-alpha"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "robot-alpha: ok" in out
    assert "installs: robot-alpha" in out


def test_no_arguments_checks_the_minimal_environment(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml)

    assert check.main([], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "minimal: ok" in out
    assert "installs: (core only)" in out


def test_a_missing_lock_is_not_a_problem(tmp_path, write_toml, capsys):
    # Locks are optional reproduction artifacts, so a missing one is not a
    # problem and does not shorten the check.
    _write_pyproject(write_toml)
    _write_component(write_toml)

    catalog = discover(tmp_path)
    assert check.check_environment("robot-alpha", catalog, tmp_path) == []
    assert check.main(["robot-alpha"], root=tmp_path) == 0
    assert "robot-alpha: ok" in capsys.readouterr().out


def test_inputs_hash_reports_the_installation_inputs(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml)

    assert check.main(["robot-alpha", "--inputs-hash"], root=tmp_path) == 0

    lines = capsys.readouterr().out.splitlines()
    digest = next(line for line in lines if line.startswith("inputs="))
    assert digest.removeprefix("inputs=")
    assert "python=3.12" in lines

    # A manifest edit changes what a reinstall would produce, so the cache key
    # must change with it.
    _write_component(write_toml, dependencies=("alpha-dep", "other-dep"))
    assert check.main(["robot-alpha", "--inputs-hash"], root=tmp_path) == 0
    changed = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("inputs=")
    )
    assert changed != digest


def test_inputs_hash_takes_one_environment(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml)

    assert check.main(["--all", "--inputs-hash"], root=tmp_path) == 2
    assert "--inputs-hash takes exactly one environment" in capsys.readouterr().err


def test_all_checks_minimal_and_every_component(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml, "alpha")
    _write_component(write_toml, "beta")

    assert check.main(["--all"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "minimal: ok" in out
    assert "robot-alpha: ok" in out
    assert "robot-beta: ok" in out


def test_a_conflict_fails_the_composed_environment(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "robot-alpha"
        probe = "json"
        env_conflicts = ["robot-beta"]
        """,
    )
    _write_component(write_toml, "beta")

    assert check.main(["robot-alpha+robot-beta"], root=tmp_path) == 1

    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "in the same environment" in out


def test_unknown_environment_is_reported(tmp_path, write_toml, capsys):
    _write_pyproject(write_toml)
    _write_component(write_toml)

    assert check.main(["missing"], root=tmp_path) == 1

    assert "unknown environment 'missing'" in capsys.readouterr().out
