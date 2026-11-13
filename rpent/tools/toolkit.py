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

"""Base class for agent tools.

``Toolkit`` is the agent-facing tool container. Subclasses can register tools
during ``__init__`` via :meth:`Toolkit.add_tool`; planners discover declarations
through :meth:`Toolkit.list_tools` and dispatch through :meth:`Toolkit.execute_tool`.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from rpent.dashboard.events import DashboardEventSink, StepRecordEvent
from rpent.session import Payload
from rpent.session.env_capture import current_tool_call
from rpent.tools.base import ExecutionStatus, Tool, ToolResult, iter_tools, tool
from rpent.tools.execution import ExecutionTrace, track_execution
from rpent.utils.logging import get_logger
from rpent.utils.templates import substitute

logger = get_logger("toolkit")

if TYPE_CHECKING:
    from rpent.memory.manager import MemoryManager
    from rpent.session import EnvState, StepRecord


@dataclass(eq=False)
class _ToolOperation:
    readonly: bool
    cancel_event: threading.Event = field(default_factory=threading.Event)
    done: bool = False


class _Scheduler:
    """Share readonly calls; run queued exclusive calls in arrival order.

    A plain RWLock only provides mutual exclusion. Tool calls also need ordered
    writers, cancellation of queued and active calls, and pause/close with drain.
    One condition keeps admission and these lifecycle transitions synchronized.
    """

    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.pending: list[_ToolOperation] = []
        self.active: set[_ToolOperation] = set()
        self.paused = False
        self.closed = False

    def acquire(self, *, readonly: bool) -> _ToolOperation:
        with self.condition:
            if self.closed:
                raise ToolCancelled("Toolkit is closed.")
            if self.paused:
                raise ToolCancelled("Tool calls are paused.")
            call = _ToolOperation(readonly=readonly)
            self.pending.append(call)
            self.condition.notify_all()
            try:
                while True:
                    if call.cancel_event.is_set():
                        raise ToolCancelled("tool operation interrupted")
                    exclusive = next(
                        (item for item in self.pending if not item.readonly), None
                    )
                    if (
                        readonly
                        and exclusive is None
                        and all(item.readonly for item in self.active)
                    ) or (not readonly and not self.active and call is exclusive):
                        self.pending.remove(call)
                        self.active.add(call)
                        return call
                    self.condition.wait()
            except BaseException:
                self.pending.remove(call)
                call.done = True
                self.condition.notify_all()
                raise

    def release(self, call: _ToolOperation) -> None:
        with self.condition:
            self.active.remove(call)
            call.done = True
            self.condition.notify_all()

    def cancel(self, *, close: bool = False) -> list[_ToolOperation]:
        with self.condition:
            self.paused = True
            self.closed |= close
            calls = [*self.pending, *self.active]
            for call in calls:
                call.cancel_event.set()
            self.condition.notify_all()
            return calls

    def wait(self, calls: list[_ToolOperation]) -> None:
        with self.condition:
            self.condition.wait_for(lambda: all(call.done for call in calls))

    def resume(self) -> None:
        with self.condition:
            if self.active or self.pending:
                raise RuntimeError("Wait for tool cleanup before resuming.")
            if not self.closed:
                self.paused = False


class ToolCancelled(Exception):
    """Raised when an environment reaches a safe cancellation boundary."""


def _failure_result(
    code: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    no_execution: bool = True,
    execution_uncertain: bool = False,
    execution_status: ExecutionStatus = "not_started",
) -> ToolResult:
    """Build a framework-level failure with explicit execution layers."""
    return ToolResult(
        data=dict(data) if data is not None else {"error": message},
        call_ok=False,
        error={"code": code, "message": message},
        no_execution=no_execution,
        execution_uncertain=execution_uncertain,
        execution_status=execution_status,
    )


def _framework_error_layers(
    trace: ExecutionTrace,
) -> tuple[bool, bool, ExecutionStatus]:
    """Layers for a framework failure after the handler ran.

    A write that was already issued may have reached the environment, so its
    outcome is unknown even when result encoding fails afterwards. Without a
    write, the framework can still assert that nothing executed.
    """
    if trace.issued:
        return False, True, "unknown"
    return True, False, "not_started"


class Toolkit:
    """Base toolkit: registers common tools and dispatches tool calls.

    Subclasses extend ``__init__`` (calling ``super().__init__()`` first)
    and register additional tools with :meth:`add_tool`. Robot-specific
    subclasses receive their env/model/etc. as constructor arguments and
    build the underlying env Primitives in ``__init__``; the toolkit
    base class only contributes the common file/IO tools. Override
    :meth:`close` to release robot-side primitives / servers at the end of the run.
    """

    def __init__(
        self,
        *,
        dashboard_events: DashboardEventSink,
        state: Any = None,
        memory: "MemoryManager",
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._dashboard_events = dashboard_events
        self._state = state
        self._memory = memory
        self._scheduler = _Scheduler()
        self._register_common_tools()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_tool(self, tool: Tool, *, replace: bool = False) -> None:
        """Register a bound declaration, explicitly opting into replacement.

        Args:
            tool: A decorated function or bound instance method.
            replace: Replace an existing declaration, for robot-specific tools
                or execution guards such as an exploration finish check.
        """
        if tool._unbound_method:
            raise TypeError("Register an instance's tool method, not an unbound method")
        if tool.name in self._tools and not replace:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def add_tools(
        self,
        *owners: Any,
        capabilities: Any = None,
        config: Any = None,
    ) -> None:
        """Register declarations from tool families and explicit tool iterables.

        A family exposes ``tools(capabilities, config)`` and trims its
        declarations to the capabilities the host actually connected. Passing
        a plain iterable of declarations keeps the older registration path.
        """
        if capabilities is not None:
            snapshot = getattr(capabilities, "as_dict", None)
            logger.info(
                "registering tool families with capabilities: %s",
                snapshot() if callable(snapshot) else capabilities,
            )
        for owner in owners:
            family = getattr(owner, "tools", None)
            if callable(family) and not isinstance(owner, Tool):
                for declaration in family(capabilities, config):
                    self.add_tool(declaration)
                continue
            if isinstance(owner, (str, bytes)) or not isinstance(owner, Iterable):
                raise TypeError(
                    "add_tools expects a tool family or an iterable of Tool "
                    f"declarations, got {type(owner).__name__}"
                )
            for declaration in owner:
                self.add_tool(declaration)

    def _register_common_tools(self) -> None:
        from rpent.tools.file_tools import FileTools

        files = FileTools(memory=self._memory)
        self._memory.check_layout()
        for declaration in iter_tools(files):
            if declaration.name in {"read_text_file", "list_dir"}:
                declaration = replace(
                    declaration,
                    description=declaration.description
                    + self._memory.file_tool_description,
                )
            self.add_tool(declaration)
        self.add_tool(self.finish)

    @tool(readonly=True)
    def finish(self, status: str, summary: str) -> ToolResult:
        """Call when the task is complete or unrecoverable. Halts the agent loop. Save any artifacts (recipe, audit) BEFORE calling finish.

        Args:
            status: Outcome, e.g. 'success', 'failure', or 'stuck'.
            summary: Short natural-language summary of the run.
        """
        return ToolResult(data={"_finish": True, "status": status, "summary": summary})

    # ------------------------------------------------------------------
    # Planner-facing API
    # ------------------------------------------------------------------

    @property
    def memory(self) -> "MemoryManager":
        """Return the run's required memory manager."""
        return self._memory

    @property
    def state(self) -> EnvState:
        """Return the run's artifact and step store."""
        if self._state is None:
            raise RuntimeError("toolkit has no environment state")
        return self._state

    def list_tools(self) -> tuple[Tool, ...]:
        """Return the native declarations with run-specific descriptions resolved."""
        return tuple(
            replace(tool, description=substitute(tool.description))
            for tool in self._tools.values()
        )

    def execute_tool(self, name: str, input_dict: dict[str, Any]) -> ToolResult:
        """Validate one call, execute it, and capture state for advancing tools.

        The returned result fills the call/execution layers: parameters that
        never reach a handler are ``call_ok=False, no_execution=True``; a
        handler that raises after an environment client issued a write is
        ``execution_uncertain``. Domain results stay in ``data``.
        """
        tool = self._tools.get(name)
        if tool is None:
            return _failure_result("unknown_tool", f"unknown tool: {name}")
        try:
            parameters = tool.args_schema.model_validate(input_dict, strict=True)
        except ValidationError as exc:
            return _failure_result(
                "validation",
                f"bad arguments for {name}",
                data={
                    "error": f"bad arguments for {name}",
                    "errors": exc.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    ),
                },
            )
        kwargs = {
            field: getattr(parameters, field) for field in type(parameters).model_fields
        }

        try:
            operation = self._scheduler.acquire(readonly=tool.readonly)
        except ToolCancelled as exc:
            return _failure_result(
                "cancelled",
                str(exc),
                data={"error": str(exc), "code": "tool_cancelled", "interrupted": True},
            )

        try:
            started = time.perf_counter()
            capture = current_tool_call.get()
            with track_execution() as trace:
                try:
                    self.raise_if_cancelled()
                    if capture is not None:
                        capture.start(action_source=tool.action_source)
                    native = tool(**kwargs)
                except TypeError as exc:
                    if trace.issued:
                        message = (
                            f"tool {name} failed after issuing a write: "
                            f"TypeError: {exc}"
                        )
                        native = _failure_result(
                            "execution_uncertain",
                            message,
                            data={"error": message, "got": input_dict},
                            no_execution=False,
                            execution_uncertain=True,
                            execution_status="unknown",
                        )
                    else:
                        native = _failure_result(
                            "validation",
                            f"bad arguments for {name}: {exc}",
                            data={
                                "error": f"bad arguments for {name}: {exc}",
                                "got": input_dict,
                            },
                        )
                except ToolCancelled as exc:
                    native = _failure_result(
                        "cancelled",
                        str(exc),
                        data={
                            "error": str(exc),
                            "code": "tool_cancelled",
                            "interrupted": True,
                        },
                        no_execution=not trace.issued,
                        execution_uncertain=trace.issued,
                        execution_status="unknown" if trace.issued else "not_started",
                    )
                except Exception as exc:
                    logger.exception("Tool %s failed", name)
                    native = _failure_result(
                        "execution_uncertain" if trace.issued else "execution_failed",
                        str(exc),
                        data={"error": str(exc), "traceback": traceback.format_exc()},
                        no_execution=not trace.issued,
                        execution_uncertain=trace.issued,
                        execution_status="unknown" if trace.issued else "not_started",
                    )

            if native.execution_status is None:
                # A call that explicitly produced no physical action must not
                # be reported as executed.
                native.execution_status = (
                    "not_started" if native.no_execution else "completed"
                )

            if capture is not None and capture.started:
                capture.result(
                    Payload(
                        format="rpent.tool_result",
                        format_version="1",
                        data={
                            "data": native.data,
                            "images": native.images,
                            "image_labels": native.image_labels,
                            "call_ok": native.call_ok,
                            "error": native.error,
                            "no_execution": native.no_execution,
                            "execution_uncertain": native.execution_uncertain,
                            "execution_status": native.execution_status,
                        },
                        completeness="complete",
                    )
                )

            if not tool.readonly and tool.captures_state:
                elapsed_s = round(time.perf_counter() - started, 2)
                # State records keep the domain payload; the call/execution
                # layers travel in the captured ``rpent.tool_result`` record.
                result_dict = dict(native.data)
                command = {"action": name, **input_dict}
                record: StepRecord | None = None
                try:
                    observed = self.get_env_state(
                        command=command,
                        result=result_dict,
                        elapsed_s=elapsed_s,
                    )
                except Exception as exc:
                    logger.exception("State capture failed after %s", name)
                    message = f"failed to capture state after {name}: {exc}"
                    native.data["state_capture_error"] = str(exc)
                    if not native.is_error:
                        native.data["error"] = message
                        native.error = {
                            "code": (
                                "execution_uncertain"
                                if trace.issued
                                else "execution_failed"
                            ),
                            "message": message,
                        }
                    native.data.setdefault("traceback", traceback.format_exc())
                    if trace.issued:
                        # Missing after-state does not tell us how much of the
                        # issued request ran, so the receipt is no longer
                        # authoritative. Keep the reported value as evidence.
                        if native.execution_status is not None:
                            native.data.setdefault(
                                "reported_execution_status", native.execution_status
                            )
                        native.no_execution = False
                        native.execution_uncertain = True
                        native.execution_status = "unknown"
                else:
                    record = self._state.latest_record()
                    if native.is_error:
                        for key, value in native.data.items():
                            observed.data.setdefault(key, value)
                        observed.data["error"] = native.data.get(
                            "error", observed.data.get("error")
                        )
                    native = replace(
                        native,
                        data=observed.data,
                        images=native.images + observed.images,
                        image_labels=native.image_labels + observed.image_labels,
                    )
                if record is not None:
                    self._publish_step(record)

            try:
                json.dumps(native.to_dict(), allow_nan=False, default=str)
            except (TypeError, ValueError) as exc:
                message = f"Tool result serialization failed: {exc}"
                no_execution, uncertain, status = _framework_error_layers(trace)
                reported_status = native.execution_status
                native = replace(
                    native,
                    data={
                        "error": message,
                        "reported_execution_status": reported_status,
                    },
                    call_ok=False,
                    error={
                        "code": (
                            "execution_uncertain"
                            if trace.issued
                            else "execution_failed"
                        ),
                        "message": message,
                    },
                    no_execution=no_execution,
                    execution_uncertain=uncertain,
                    execution_status=status,
                )
            if capture is not None:
                cancelled = native.error is not None and (
                    native.error.get("code") == "cancelled"
                )
                capture.finish(
                    "cancelled"
                    if cancelled or native.data.get("code") == "tool_cancelled"
                    else "failed"
                    if native.is_error
                    else "completed",
                    str(native.data.get("error", "")),
                )
            return native
        finally:
            self._scheduler.release(operation)

    def _publish_step(self, record: StepRecord) -> None:
        """Publish one recorded environment step to the dashboard sink."""
        self._dashboard_events.emit(
            StepRecordEvent(
                record=record,
                env_state=self._state,
            )
        )

    def get_env_state(
        self,
        *,
        command: dict[str, Any],
        result: dict[str, Any],
        elapsed_s: float,
    ) -> ToolResult:
        """Capture and return the observation produced by a stateful tool."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Server lifecycle hooks (overridden by robot toolkits)
    # ------------------------------------------------------------------

    def cancel_active_and_wait(self) -> None:
        """Pause admission, cancel queued and active calls, and wait for cleanup."""
        self._scheduler.wait(self._scheduler.cancel())

    def resume_calls(self) -> None:
        """Reopen admission after interrupted calls and their workers have drained."""
        self._scheduler.resume()

    def raise_if_cancelled(self) -> None:
        """Raise at an environment-defined safe cancellation boundary."""
        with self._scheduler.condition:
            if any(call.cancel_event.is_set() for call in self._scheduler.active):
                raise ToolCancelled("tool operation interrupted")

    def close(self) -> None:
        """Close admission and drain calls before subclasses release resources."""
        self._scheduler.cancel(close=True)
        self.cancel_active_and_wait()

    def exploration_continuation(self, *, explicit: bool = False) -> str | None:
        """Return a rule-checked continuation at an idle planner boundary."""
        return None

    def solved(self) -> bool:
        """Whether the env has reported the task complete.

        Ground truth for the session loop: an agent may call ``finish`` with
        ``status="success"`` on a cell it did not actually finish, so the
        handoff decision reads the environment, not the agent.
        """
        raise NotImplementedError

    def evaluation_metrics(self, *, success: bool | None) -> dict[str, Any]:
        """Collect run metrics after tools drain and before runtime shutdown.

        Args:
            success: The environment verdict collected for this episode.

        Returns:
            Robot-specific metrics for result artifacts, not planner feedback.
        """
        return {}

    def write_recipe(self, recipe_tag: str) -> str | None:
        """Write a replay recipe for this robot, if supported."""
        return None
