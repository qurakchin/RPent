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

"""Offline contracts for the RoboDojo toolkit and its task-gated tool surface.

The agent must only be told about tools the toolkit actually exposes for the
running task. ``task_tool_names`` is the single source of truth: the toolkit
registers exactly those names and the system prompt advertises exactly those
names (plus the shared file/IO tools).
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from robots.robodojo import robot_spec, toolkit
from robots.robodojo import tools as robodojo_tools
from robots.robodojo.prompts import system as system_prompts
from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.tools.toolkit import Toolkit
from rpent.utils import templates

COMMON_TOOLS = {"read_text_file", "write_text_file", "list_dir", "finish"}
ROBODOJO_TOOLS = {spec["name"] for spec in robodojo_tools.TOOLS_SPEC}
TASKS = (
    "put_bottles_into_dustbin",
    "fill_pen_holder",
    "stack_bowls_random",
)

BuildToolkit = Callable[[str], Toolkit]


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        step_idx=0,
        terminated=False,
        truncated=False,
        state={},
        artifacts=set(),
        extras={},
        command=None,
        result=None,
        elapsed_s=None,
    )


def _tool_names(robot_toolkit: Toolkit) -> set[str]:
    return {spec["name"] for spec in robot_toolkit.get_tools_spec()}


@pytest.fixture
def build_toolkit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> BuildToolkit:
    monkeypatch.setattr(toolkit, "get_output_dir", lambda: tmp_path)
    monkeypatch.setattr(
        templates, "default_variables", lambda: {"output_dir": "/offline/output"}
    )
    monkeypatch.setattr(robodojo_tools, "dump_state", lambda *args, **kwargs: _record())

    def _build(task: str) -> Toolkit:
        return toolkit.RoboDojoToolkit(
            primitives_kwargs={"env": SimpleNamespace(), "task": task},
            dashboard_events=NullDashboardEventSink(),
            memory=MemoryManager(tmp_path / "memory"),
        )

    return _build


def test_task_tool_names_stay_within_the_declared_catalog() -> None:
    for task in TASKS:
        names = robodojo_tools.task_tool_names(task)
        assert len(names) == len(set(names))
        assert set(names) <= ROBODOJO_TOOLS


def test_put_bottles_exposes_every_declared_robodojo_tool(
    build_toolkit: BuildToolkit,
) -> None:
    exposed = _tool_names(build_toolkit("put_bottles_into_dustbin"))

    assert exposed == COMMON_TOOLS | ROBODOJO_TOOLS


def test_toolkit_exposes_exactly_the_task_tool_names(
    build_toolkit: BuildToolkit,
) -> None:
    for task in TASKS:
        exposed = _tool_names(build_toolkit(task))
        assert exposed == COMMON_TOOLS | set(robodojo_tools.task_tool_names(task))


def test_prompt_advertises_exactly_the_toolkit_surface(
    build_toolkit: BuildToolkit,
) -> None:
    for task in TASKS:
        exposed = _tool_names(build_toolkit(task))
        advertised = set(
            re.findall(r"`([a-z0-9_]+)`", system_prompts.tool_access(task))
        )
        assert advertised == exposed


def test_bin_primitive_is_gated_to_put_bottles(build_toolkit: BuildToolkit) -> None:
    assert "place_in_bin" in _tool_names(build_toolkit("put_bottles_into_dustbin"))
    assert "place_in_bin" not in _tool_names(build_toolkit("fill_pen_holder"))


def test_registry_tool_spec_is_the_single_source_of_truth() -> None:
    dashboard_primitives = set(robot_spec.get_robot_spec().dashboard["primitives"])

    assert dashboard_primitives == ROBODOJO_TOOLS
