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

"""``check`` reports broken targets and stale locks without installing."""

from rpent.install.discovery import discover
from tests.tooling import check


def _write_target(write_toml, name, *, lock=None, core=False, write_lock=True):
    declared = f'lock = "{lock}"\n' if lock else ""
    core_line = f"core = {str(core).lower()}\n"
    write_toml(
        f"installs/targets/{name}.toml",
        f"""
        schema = 2
        kind = "target"
        name = "{name}"
        python = "3.11"
        {declared}{core_line}
        [components.alpha]
        placement = "in-env"
        """,
    )
    if write_lock:
        # Every target installs from a lock; an undeclared one defaults to
        # ``locks/<name>.lock`` beside its target directory.
        write_toml(lock or f"installs/locks/{name}.lock", "alpha-dep==1.0.0")


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


def test_missing_declared_lock_fails_the_target(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(
        write_toml,
        "alpha-env",
        lock="installs/locks/alpha-env.lock",
        write_lock=False,
    )

    catalog = discover(tmp_path)
    problems = check.check_target("alpha-env", catalog, tmp_path)

    assert any("does not exist" in problem for problem in problems)
    assert check.main(["alpha-env"], root=tmp_path) == 1
    assert "target alpha-env: FAIL" in capsys.readouterr().out


def test_all_checks_every_target(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    write_toml("installs/locks/alpha.lock", "alpha-dep==1.0.0")
    _write_target(write_toml, "alpha-env")
    _write_target(write_toml, "alpha-env-2")

    assert check.main(["--all"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert "target alpha-env: ok" in out
    assert "target alpha-env-2: ok" in out
    # The component itself forms a target, so --all checks it too.
    assert "target alpha: ok" in out


def test_unknown_target_is_reported(tmp_path, write_toml, capsys):
    _write_component(write_toml)
    _write_target(write_toml, "alpha-env")

    assert check.main(["missing"], root=tmp_path) == 1

    assert "unknown target 'missing'" in capsys.readouterr().err
