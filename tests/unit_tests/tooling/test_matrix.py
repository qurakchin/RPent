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

"""Every environment must be installed by exactly one full-CI runner."""

import json

from rpent.install.discovery import discover_components
from tests.tooling import matrix


def _write_component(root, name):
    path = root / "robots" / name / "component.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'schema = 2\nname = "robot-{name}"\nprobe = "json"\n',
        encoding="utf-8",
    )
    return path


def test_environment_without_a_runner_is_reported(tmp_path):
    _write_component(tmp_path, "alpha")

    problems = matrix.problems(
        discover_components(tmp_path),
        {"hosted": ("minimal",), "gpu": ()},
        root=tmp_path,
    )

    assert problems == [
        "environment 'robot-alpha' (robots/alpha) is not installed by any "
        "runner; add it to HOSTED or GPU in tests/tooling/matrix.py"
    ]


def test_the_core_only_environment_is_installed_like_any_other(tmp_path):
    # ``minimal`` installs no component but still has to be assigned, so a new
    # runner partition cannot leave the core-only environment unbuilt.
    _write_component(tmp_path, "alpha")

    problems = matrix.problems(
        discover_components(tmp_path),
        {"hosted": ("robot-alpha",), "gpu": ()},
        root=tmp_path,
    )

    assert problems == [
        "environment 'minimal' (minimal) is not installed by any runner; "
        "add it to HOSTED or GPU in tests/tooling/matrix.py"
    ]


def test_stale_table_entry_is_reported(tmp_path):
    _write_component(tmp_path, "alpha")

    problems = matrix.problems(
        discover_components(tmp_path), {"hosted": ("minimal", "robot-alpha", "removed")}
    )

    assert problems == [
        "hosted lists environment 'removed', but no component manifest "
        "declares it; remove it from tests/tooling/matrix.py"
    ]


def test_environment_assigned_to_two_runners_is_reported(tmp_path):
    _write_component(tmp_path, "alpha")

    problems = matrix.problems(
        discover_components(tmp_path),
        {"hosted": ("minimal", "robot-alpha"), "gpu": ("robot-alpha",)},
    )

    assert problems == [
        "environment 'robot-alpha' is assigned to both gpu and hosted; "
        "keep it on one runner"
    ]


def test_runner_listed_twice_is_reported(tmp_path):
    _write_component(tmp_path, "alpha")

    problems = matrix.problems(
        discover_components(tmp_path),
        {"hosted": ("minimal", "robot-alpha", "robot-alpha"), "gpu": ()},
    )

    assert problems == ["hosted lists environment 'robot-alpha' more than once"]


def test_check_reports_drift_and_fails(tmp_path, capsys):
    _write_component(tmp_path, "alpha")

    assert matrix.main(["--check"], root=tmp_path) == 1
    assert "not installed by any runner" in capsys.readouterr().err


def test_check_passes_when_the_partition_matches(tmp_path, monkeypatch, capsys):
    _write_component(tmp_path, "alpha")
    monkeypatch.setattr(
        matrix, "MATRICES", {"hosted": ("minimal", "robot-alpha"), "gpu": ()}
    )

    assert matrix.main(["--check"], root=tmp_path) == 0
    assert capsys.readouterr().err == ""


def test_runner_prints_the_selected_partition(monkeypatch, capsys):
    monkeypatch.setattr(matrix, "MATRICES", {"hosted": ("alpha",), "gpu": ()})

    assert matrix.main(["--runner", "hosted"]) == 0

    assert json.loads(capsys.readouterr().out) == ["alpha"]
