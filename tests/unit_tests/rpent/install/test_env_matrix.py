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

"""Every profile must be installed by exactly one nightly runner."""

import importlib.util
import json
from pathlib import Path

from rpent.install.discovery import discover_profiles

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "env_matrix.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("env_matrix", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


env_matrix = _load_script()


def _write_profile(root, name):
    path = root / "envs" / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'schema = 1\nname = "{name}"\npython = "3.11"\nplatform = "linux-x86_64"\n',
        encoding="utf-8",
    )
    return path


def test_repository_partition_covers_every_profile():
    assert env_matrix.problems(discover_profiles(REPO_ROOT)) == []


def test_profile_without_a_runner_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = env_matrix.problems(
        discover_profiles(tmp_path), {"hosted": (), "gpu": ()}
    )

    assert problems == [
        "profile 'alpha' (envs/alpha.toml) is not installed by any nightly "
        "runner; add it to HOSTED or GPU in scripts/env_matrix.py"
    ]


def test_stale_table_entry_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = env_matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha", "removed"), "gpu": ()}
    )

    assert problems == [
        "hosted lists profile 'removed', but envs/removed.toml does not exist; "
        "remove it from scripts/env_matrix.py"
    ]


def test_profile_assigned_to_two_runners_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = env_matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha",), "gpu": ("alpha",)}
    )

    assert problems == [
        "profile 'alpha' is assigned to both gpu and hosted; keep it on one runner"
    ]


def test_runner_listed_twice_is_reported(tmp_path):
    _write_profile(tmp_path, "alpha")

    problems = env_matrix.problems(
        discover_profiles(tmp_path), {"hosted": ("alpha", "alpha"), "gpu": ()}
    )

    assert problems == ["hosted lists profile 'alpha' more than once"]


def test_check_reports_drift_and_fails(tmp_path, capsys):
    _write_profile(tmp_path, "alpha")

    assert env_matrix.main(["--check", "--root", str(tmp_path)]) == 1
    assert "not installed by any nightly runner" in capsys.readouterr().err

    assert env_matrix.main(["--check", "--root", str(REPO_ROOT)]) == 0


def test_runner_prints_the_workflow_matrix(capsys):
    assert env_matrix.main(["--runner", "hosted"]) == 0

    assert json.loads(capsys.readouterr().out) == list(env_matrix.HOSTED)
