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

"""Call and execution layers for framework-dispatched tool results."""

from __future__ import annotations

from pathlib import Path

from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.tools import Toolkit, ToolResult, tool
from rpent.tools.execution import mark_write_issued
from rpent.tools.toolkit import ToolCancelled


class _Toolkit(Toolkit):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(
            dashboard_events=NullDashboardEventSink(),
            memory=MemoryManager(tmp_path / "memory"),
        )


def test_unknown_tool_and_invalid_arguments_never_reach_a_handler(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def probe(value: int) -> ToolResult:
        """Return the value."""
        return ToolResult(data={"value": value})

    toolkit.add_tool(probe)

    unknown = toolkit.execute_tool("missing", {})
    invalid = toolkit.execute_tool("probe", {"value": "text"})

    assert unknown.call_ok is False
    assert unknown.no_execution is True
    assert unknown.execution_uncertain is False
    assert unknown.execution_status == "not_started"
    assert unknown.error == {"code": "unknown_tool", "message": "unknown tool: missing"}
    assert invalid.call_ok is False
    assert invalid.no_execution is True
    assert invalid.error["code"] == "validation"
    assert invalid.execution_status == "not_started"


def test_handler_failure_before_a_write_is_a_failed_call_without_execution(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def fail() -> ToolResult:
        """Raise before touching the environment."""
        raise RuntimeError("planning exploded")

    toolkit.add_tool(fail)
    result = toolkit.execute_tool("fail", {})

    assert result.call_ok is False
    assert result.error["code"] == "execution_failed"
    assert result.no_execution is True
    assert result.execution_uncertain is False
    assert result.execution_status == "not_started"
    assert result.data["error"] == "planning exploded"


def test_handler_failure_after_a_write_is_execution_uncertain(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def fail_after_write() -> ToolResult:
        """Write, then lose the response."""
        mark_write_issued("step")
        raise RuntimeError("response lost")

    toolkit.add_tool(fail_after_write)
    result = toolkit.execute_tool("fail_after_write", {})

    assert result.call_ok is False
    assert result.error["code"] == "execution_uncertain"
    assert result.no_execution is False
    assert result.execution_uncertain is True
    assert result.execution_status == "unknown"
    assert result.to_dict()["execution_uncertain"] is True


def test_cancellation_after_a_write_keeps_the_uncertain_execution_layer(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def interrupt() -> ToolResult:
        """Write, then report a safe cancellation boundary."""
        mark_write_issued("chunk_step")
        raise ToolCancelled("interrupted")

    toolkit.add_tool(interrupt)
    result = toolkit.execute_tool("interrupt", {})

    assert result.call_ok is False
    assert result.error["code"] == "cancelled"
    assert result.execution_uncertain is True
    assert result.no_execution is False
    assert result.execution_status == "unknown"


def test_domain_error_keeps_call_ok_true_and_marks_the_call_completed(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def refuse() -> ToolResult:
        """Return a domain-level refusal."""
        return ToolResult(data={"error": "target is not visible"})

    toolkit.add_tool(refuse)
    result = toolkit.execute_tool("refuse", {})

    assert result.call_ok is True
    assert result.error is None
    assert result.is_error is True
    assert result.data["error"] == "target is not visible"
    assert result.execution_status == "completed"
    assert result.to_dict()["call_ok"] is True


def test_successful_call_reports_completed_without_extra_layers(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def read() -> ToolResult:
        """Return a value."""
        return ToolResult(data={"value": 3})

    toolkit.add_tool(read)
    result = toolkit.execute_tool("read", {})

    assert result.call_ok is True
    assert result.no_execution is False
    assert result.execution_uncertain is False
    assert result.execution_status == "completed"
    assert result.to_dict() == {
        "value": 3,
        "call_ok": True,
        "execution_status": "completed",
    }
