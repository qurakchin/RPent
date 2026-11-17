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

"""Every profile must be installed by exactly one full-CI runner."""

import json
from pathlib import Path

from rpent.install import matrix
from rpent.install.discovery import discover_profiles

REPO_ROOT = Path(__file__).resolve().parents[4]


def _write_profile(root, name):
    path = root / "installs" / "profiles" / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'schema = 1\nname = "{name}"\npython = "3.11"\nplatform = "linux-x86_64"\n',
        encoding="utf-8",
    )
    return path


def test_repository_partition_covers_every_profile():
    assert matrix.problems(discover_profiles(REPO_ROOT)) == []


def test_profile_without_a_runner_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = matrix.problems(discover_profiles(tmp_path), {"hosted": (), "gpu": ()})

    assert problems == [
        "profile 'alpha' (installs/profiles/alpha.toml) is not installed by any "
        "runner; add it to HOSTED or GPU in rpent/install/matrix.py"
    ]


def test_stale_table_entry_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha", "removed"), "gpu": ()}
    )

    assert problems == [
        "hosted lists profile 'removed', but installs/profiles/removed.toml does "
        "not exist; remove it from rpent/install/matrix.py"
    ]


def test_profile_assigned_to_two_runners_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha",), "gpu": ("alpha",)}
    )

    assert problems == [
        "profile 'alpha' is assigned to both gpu and hosted; keep it on one runner"
    ]


def test_runner_listed_twice_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha", "alpha"), "gpu": ()}
    )

    assert problems == ["hosted lists profile 'alpha' more than once"]


def test_check_reports_drift_and_fails(tmp_path, capsys):
    _write_profile(tmp_path, "alpha")

    assert matrix.main(["--check"], root=tmp_path) == 1
    assert "not installed by any runner" in capsys.readouterr().err

    assert matrix.main(["--check"], root=REPO_ROOT) == 0


def test_runner_prints_the_workflow_matrix(capsys):
    assert matrix.main(["--runner", "hosted"]) == 0

    assert json.loads(capsys.readouterr().out) == list(matrix.HOSTED)
