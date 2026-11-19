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

"""``check`` reports broken targets without installing and never needs a lock."""

import pytest

from rpent.install.discovery import discover
from tests.tooling import check


def _write_target(write_toml, name, *, core=False):
    core_line = f"core = {str(core).lower()}\n"
    write_toml(
        f"installs/targets/{name}.toml",
        f"""
        schema = 2
        kind = "target"
        name = "{name}"
        python = "3.11"
        {core_line}
        [components.alpha]
        """,
    )


def _write_component(write_toml):
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "json"
        python = "3.11"
        core = false
        dependencies = ["alpha-dep"]
        """,
    )


def test_valid_target_reports_what_it_installs(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    assert check.main(["alpha-env"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "target alpha-env: ok" in out
    assert "installs: alpha" in out


def test_a_target_without_a_lock_is_valid(tmp_path, write_toml, capsys):
    # Locks are optional reproduction artifacts, so a missing one is not a
    # problem and does not shorten the check.
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    catalog = discover(tmp_path)
    assert check.check_target("alpha-env", catalog, tmp_path) == []
    assert check.main(["alpha-env"], root=tmp_path) == 0
    assert "target alpha-env: ok" in capsys.readouterr().out


def test_inputs_hash_reports_the_installation_inputs(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    assert check.main(["alpha-env", "--inputs-hash"], root=tmp_path) == 0

    lines = capsys.readouterr().out.splitlines()
    digest = next(line for line in lines if line.startswith("inputs="))
    assert digest.removeprefix("inputs=")
    assert "python=3.11" in lines

    # A manifest edit changes what a reinstall would produce, so the cache key
    # must change with it.
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "json"
        python = "3.11"
        core = false
        dependencies = ["alpha-dep", "other-dep"]
        """,
    )
    assert check.main(["alpha-env", "--inputs-hash"], root=tmp_path) == 0
    changed = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("inputs=")
    )
    assert changed != digest


def test_inputs_hash_takes_one_target(tmp_path, write_toml):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    with pytest.raises(SystemExit):
        check.main(["--all", "--inputs-hash"], root=tmp_path)


def test_all_checks_every_target(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")
    _write_target(write_toml, "alpha-env-2")

    assert check.main(["--all"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "target alpha-env: ok" in out
    assert "target alpha-env-2: ok" in out
    # Robots install only through a target, so no same-name target exists.
    assert "target alpha: ok" not in out


def test_a_robot_without_a_target_fails_the_catalog(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    write_toml(
        "installs/targets/minimal.toml",
        """
        schema = 2
        kind = "target"
        name = "minimal"
        python = "3.11"
        core = false

        [components]
        """,
    )

    assert check.main(["--all"], root=tmp_path) == 1

    out = capsys.readouterr().out
    assert "catalog: FAIL" in out
    assert "robots/alpha/component.toml is not selected by any target" in out


def test_unknown_target_is_reported(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    assert check.main(["missing"], root=tmp_path) == 1

    assert "unknown target 'missing'" in capsys.readouterr().err
