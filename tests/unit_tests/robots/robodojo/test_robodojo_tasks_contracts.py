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

"""Offline contracts for the RoboDojo task inventory (globbing + validation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from robots.robodojo import tasks

TASK_CONFIG_SUBPATH = Path("task") / "RoboDojo" / "config"

SUMMARY_BODY = """Rigid:
  - category:
      - label: [bottle]
      - name: dustbin
Articulation:
  - category:
      - label: [microwave]
"""


def _write_config(root: Path, name: str, body: str = "Rigid: []\n") -> Path:
    config_dir = root / TASK_CONFIG_SUBPATH
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"{name}.yml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def configured_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    root = tmp_path / "robodojo-src"
    _write_config(root, "_task")
    _write_config(root, "b_task")
    _write_config(root, "a_task", SUMMARY_BODY)
    (root / TASK_CONFIG_SUBPATH / "notes.txt").write_text("ignore me", encoding="utf-8")
    monkeypatch.setenv("ROBODOJO_SOURCE_ROOT", str(root))
    return root


def test_list_tasks_globs_yml_and_skips_the_task_template(
    configured_workspace: Path,
) -> None:
    assert tasks.is_available() is True
    assert tasks.list_tasks() == ["a_task", "b_task"]


def test_task_config_path_resolves_under_the_workspace(
    configured_workspace: Path,
) -> None:
    expected = configured_workspace / TASK_CONFIG_SUBPATH / "a_task.yml"

    assert tasks.task_config_path("a_task") == expected


def test_validate_task_accepts_known_and_rejects_unknown(
    configured_workspace: Path,
) -> None:
    assert tasks.validate_task("a_task") is None
    error = tasks.validate_task("nope")
    assert error is not None
    assert "unknown RoboDojo task" in error
    assert "a_task" in error
    assert "b_task" in error


def test_task_summary_parses_object_categories(configured_workspace: Path) -> None:
    summary = tasks.task_summary("a_task")

    assert summary["task"] == "a_task"
    assert summary["rigid"] == ["bottle", "dustbin"]
    assert summary["articulation"] == ["microwave"]


def test_task_summary_reports_a_missing_config(configured_workspace: Path) -> None:
    summary = tasks.task_summary("missing_task")

    assert summary["task"] == "missing_task"
    assert "error" in summary


def test_validation_is_deferred_when_the_workspace_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ROBODOJO_SOURCE_ROOT", str(tmp_path / "absent"))
    monkeypatch.setattr(tasks, "_warned_unconfigured", False)

    assert tasks.is_available() is False
    assert tasks.list_tasks() == []
    with pytest.warns(RuntimeWarning, match="validation is deferred"):
        assert tasks.validate_task("anything") is None
