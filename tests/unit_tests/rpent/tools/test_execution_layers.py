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

import asyncio
from pathlib import Path

from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.session.base import EnvState
from rpent.session.env_capture import ToolCallCapture
from rpent.tools import Toolkit, ToolResult, tool
from rpent.tools.execution import (
    WriteRequest,
    mark_write_issued,
    track_execution,
    writes_issued,
)
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


def test_explicit_no_execution_is_not_reported_as_completed(tmp_path: Path) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def refuse_before_write() -> ToolResult:
        """Report a request that never reached the environment."""
        return ToolResult(
            data={"error": "target is unreachable"},
            no_execution=True,
            call_ok=True,
        )

    toolkit.add_tool(refuse_before_write)
    result = toolkit.execute_tool("refuse_before_write", {})

    assert result.no_execution is True
    assert result.execution_status == "not_started"
    assert result.to_dict()["execution_status"] == "not_started"


def test_serialization_failure_without_a_write_stays_not_started(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def unencodable() -> ToolResult:
        """Return a value that cannot be encoded as strict JSON."""
        return ToolResult(data={"value": float("nan")})

    toolkit.add_tool(unencodable)
    result = toolkit.execute_tool("unencodable", {})

    assert result.call_ok is False
    assert result.error["code"] == "execution_failed"
    assert result.no_execution is True
    assert result.execution_uncertain is False
    assert result.execution_status == "not_started"
    assert result.data["reported_execution_status"] == "completed"
    assert "serialization failed" in result.data["error"]


def test_serialization_failure_after_a_write_is_execution_uncertain(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def unencodable_after_write() -> ToolResult:
        """Write, then return a result that cannot be encoded."""
        mark_write_issued("step")
        return ToolResult(data={"value": float("nan")})

    toolkit.add_tool(unencodable_after_write)
    result = toolkit.execute_tool("unencodable_after_write", {})

    assert result.call_ok is False
    assert result.error["code"] == "execution_uncertain"
    assert result.no_execution is False
    assert result.execution_uncertain is True
    assert result.execution_status == "unknown"
    assert result.data["reported_execution_status"] == "completed"


def test_state_capture_failure_after_a_write_is_execution_uncertain(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool
    def write_then_capture_fails() -> ToolResult:
        """Write, then let the framework fail to capture the after-state."""
        mark_write_issued("step")
        return ToolResult(data={"value": 3}, execution_status="completed")

    toolkit.add_tool(write_then_capture_fails)
    result = toolkit.execute_tool("write_then_capture_fails", {})

    assert result.execution_uncertain is True
    assert result.no_execution is False
    assert result.execution_status == "unknown"
    assert result.error["code"] == "execution_uncertain"
    assert result.data["reported_execution_status"] == "completed"
    assert "state_capture_error" in result.data


def test_state_capture_failure_without_a_write_keeps_the_reported_layer(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool
    def capture_fails_without_a_write() -> ToolResult:
        """Report no execution, then let state capture fail."""
        return ToolResult(
            data={"value": 3},
            no_execution=True,
            execution_status="not_started",
        )

    toolkit.add_tool(capture_fails_without_a_write)
    result = toolkit.execute_tool("capture_fails_without_a_write", {})

    assert result.execution_uncertain is False
    assert result.no_execution is True
    assert result.execution_status == "not_started"
    assert result.error["code"] == "execution_failed"
    assert "state_capture_error" in result.data


def test_type_error_after_a_write_is_not_reported_as_validation(
    tmp_path: Path,
) -> None:
    toolkit = _Toolkit(tmp_path)

    @tool(readonly=True)
    def raises_type_error_after_write() -> ToolResult:
        """Write, then fail with a TypeError from the handler."""
        mark_write_issued("step")
        raise TypeError("handler bug")

    toolkit.add_tool(raises_type_error_after_write)
    result = toolkit.execute_tool("raises_type_error_after_write", {})

    assert result.error["code"] == "execution_uncertain"
    assert result.no_execution is False
    assert result.execution_uncertain is True
    assert result.execution_status == "unknown"


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


def test_write_requests_keep_issue_order_and_transport_identity() -> None:
    with track_execution("episode-1") as trace:
        mark_write_issued("reset", request_id="req-1")
        mark_write_issued("step")
        assert writes_issued() is True

    assert trace.episode_id == "episode-1"
    assert trace.requests == [
        WriteRequest(kind="reset", sequence=0, request_id="req-1"),
        WriteRequest(kind="step", sequence=1, request_id=None),
    ]
    assert trace.writes == ["reset", "step"]
    assert writes_issued() is False


def test_write_marks_outside_a_trace_are_ignored() -> None:
    mark_write_issued("step")

    assert writes_issued() is False


def test_track_execution_attaches_and_clears_the_capture_ledger(
    tmp_path: Path,
) -> None:
    capture = ToolCallCapture(EnvState(tmp_path / "state"), "T1")

    with capture.bind():
        with track_execution() as trace:
            assert capture.execution_trace is trace
            mark_write_issued("step")

    assert capture.execution_trace is None
    assert trace.writes == ["step"]


def test_write_ledger_follows_the_capture_into_a_worker_thread(
    tmp_path: Path,
) -> None:
    capture = ToolCallCapture(EnvState(tmp_path / "state"), "T1")

    with capture.bind(), track_execution("episode-1") as trace:
        # ``asyncio.to_thread`` copies the calling context, which carries the
        # capture and therefore the write ledger.
        asyncio.run(asyncio.to_thread(mark_write_issued, "step", request_id="req-1"))

    assert trace.writes == ["step"]
    assert trace.requests[0].request_id == "req-1"
