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

"""The lock tool writes every target's lock and reports drift."""

import os
import stat

import pytest

from rpent.install.lock import LOCK_TIMESTAMP_PREFIX, lock_timestamp
from tests.tooling import lock


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
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "model"
        probe = "json"
        python = "3.11"
        dependencies = ["numpy>=2"]
        """,
    )
    write_toml(
        "tests/targets/tool-beta.toml",
        """
        schema = 2
        kind = "target"
        name = "tool-beta"
        python = "3.11"
        core = false
        dependencies = ["packaging"]

        [components]
        """,
    )
    return tmp_path


@pytest.fixture
def fake_uv(tmp_path, monkeypatch):
    """A uv stand-in that copies the compiled requirements to --output-file."""
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


def _arguments(fake_uv):
    return (fake_uv.parent / "uv-args").read_text(encoding="utf-8").splitlines()


def test_write_records_the_resolved_requirements(repo, fake_uv, capsys):
    assert lock.main(["alpha"], root=repo) == 0

    destination = repo / "tests/locks/alpha.lock"
    text = destination.read_text(encoding="utf-8")
    assert "packaging" in text
    assert "numpy>=2" in text
    assert text.startswith("# python = 3.11\n")
    assert lock_timestamp(text) is not None
    assert "locked alpha: tests/locks/alpha.lock" in capsys.readouterr().out
    arguments = _arguments(fake_uv)
    assert arguments[arguments.index("--exclude-newer") + 1] == lock_timestamp(text)


def test_write_compiles_from_the_checkout(repo, fake_uv, monkeypatch):
    # uv discovers ``[tool.uv]`` from its working directory, so a lock compiled
    # from a subdirectory would record versions the checkout does not select.
    monkeypatch.chdir(repo / "components")

    assert lock.main(["alpha"], root=repo) == 0

    assert (repo / "uv-pwd").read_text(encoding="utf-8").splitlines() == [
        str(repo.resolve())
    ]


def test_write_never_compiles_into_the_previous_lock_file(repo, fake_uv):
    # uv seeds resolution from an existing --output-file, so compiling straight
    # into the tracked lock can keep versions the current index no longer
    # selects and leave `--check` disagreeing with `lock`.
    destination = repo / "tests/locks/alpha.lock"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("packaging==0.0.0\n", encoding="utf-8")

    assert lock.main(["alpha"], root=repo) == 0

    arguments = _arguments(fake_uv)
    output = arguments[arguments.index("--output-file") + 1]
    assert output != str(destination)
    assert "numpy>=2" in destination.read_text(encoding="utf-8")


def test_write_resolves_override_files_against_the_checkout(repo, fake_uv, write_toml):
    write_toml(
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "model"
        probe = "json"
        python = "3.11"
        dependencies = ["numpy>=2"]
        overrides = ["requirements/override.txt"]
        """,
    )
    write_toml("components/models/alpha/requirements/override.txt", "numpy<3\n")

    assert lock.main(["alpha"], root=repo) == 0

    arguments = _arguments(fake_uv)
    value = arguments[arguments.index("--overrides") + 1]
    assert value == str(repo / "components/models/alpha/requirements/override.txt")
    assert os.path.isabs(value)


def test_all_writes_every_lock_under_tests(repo, fake_uv):
    assert lock.main(["--all"], root=repo) == 0

    assert (repo / "tests/locks/alpha.lock").is_file()
    assert (repo / "tests/locks/tool-beta.lock").is_file()


def test_unknown_target_is_reported(repo, fake_uv, capsys):
    assert lock.main(["missing"], root=repo) == 1

    assert "unknown target 'missing'" in capsys.readouterr().err


def test_check_passes_for_an_unchanged_lock(repo, fake_uv, capsys):
    lock.main(["alpha"], root=repo)
    capsys.readouterr()

    assert lock.main(["alpha", "--check"], root=repo) == 0
    assert "lock ok: alpha" in capsys.readouterr().out


def test_check_reports_a_stale_lock(repo, fake_uv, capsys):
    lock.main(["alpha"], root=repo)
    destination = repo / "tests/locks/alpha.lock"
    destination.write_text(
        f"{LOCK_TIMESTAMP_PREFIX}2026-11-16T00:00:00Z\nstale\n", encoding="utf-8"
    )
    capsys.readouterr()

    assert lock.main(["alpha", "--check"], root=repo) == 1
    output = capsys.readouterr().out
    assert "lock is out of date for alpha" in output
    assert "stale" in output


def test_check_rejects_a_lock_without_a_timestamp(repo, fake_uv, capsys):
    destination = repo / "tests/locks/alpha.lock"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("packaging==24.0\n", encoding="utf-8")

    assert lock.main(["alpha", "--check"], root=repo) == 1
    output = capsys.readouterr().out
    assert "lock alpha: FAIL" in output
    assert "has no '# exclude_newer =' header" in output


def test_check_recompiles_at_the_recorded_timestamp(repo, fake_uv, capsys):
    lock.main(["alpha"], root=repo)
    recorded = lock_timestamp(
        (repo / "tests/locks/alpha.lock").read_text(encoding="utf-8")
    )
    capsys.readouterr()

    assert lock.main(["alpha", "--check"], root=repo) == 0
    arguments = _arguments(fake_uv)
    assert arguments[arguments.index("--exclude-newer") + 1] == recorded


def test_check_reports_a_missing_lock(repo, fake_uv, capsys):
    assert lock.main(["alpha", "--check"], root=repo) == 1
    assert "missing lock: tests/locks/alpha.lock" in capsys.readouterr().out


def test_check_reports_a_lock_that_is_not_utf8(repo, fake_uv, capsys):
    lock.main(["alpha"], root=repo)
    (repo / "tests/locks/alpha.lock").write_bytes(b"packaging\n\xff\n")
    capsys.readouterr()

    assert lock.main(["alpha", "--check"], root=repo) == 1
    output = capsys.readouterr().out
    assert "lock alpha: FAIL" in output
    assert "not UTF-8" in output


def test_all_reports_failures_and_continues(repo, fake_uv, write_toml, capsys):
    write_toml(
        "robots/gamma/component.toml",
        """
        schema = 2
        name = "gamma"
        kind = "robot"
        probe = "json"
        python = ">=3.12"
        """,
    )
    write_toml(
        "installs/targets/gamma-env.toml",
        """
        schema = 2
        kind = "target"
        name = "gamma-env"
        python = "3.11"

        [components.gamma]
        """,
    )

    assert lock.main(["--all"], root=repo) == 1

    output = capsys.readouterr().out
    assert "lock gamma-env: FAIL" in output
    assert "no supported version" in output
    assert (repo / "tests/locks/alpha.lock").is_file()
