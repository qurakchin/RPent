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

"""Track whether a tool call issued a state-changing environment request.

The toolkit starts one trace per call. Environment clients mark a write before
sending a request, so a crash after that point reports ``execution_uncertain``
instead of claiming that nothing ran.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from rpent.session.env_capture import current_tool_call


@dataclass(frozen=True)
class WriteRequest:
    """One state-changing request issued during a tool call.

    ``sequence`` orders requests within the call. ``request_id`` is reserved
    for the execution receipt (a_6); the client supplies it when the transport
    exposes one.
    """

    kind: str
    sequence: int
    request_id: str | None = None


@dataclass
class ExecutionTrace:
    """State-changing requests issued by one tool call."""

    episode_id: str | None = None
    requests: list[WriteRequest] = field(default_factory=list)

    @property
    def writes(self) -> list[str]:
        """Operation names in issue order, for logs and legacy callers."""
        return [request.kind for request in self.requests]

    @property
    def issued(self) -> bool:
        """Whether any environment write has been issued."""
        return bool(self.requests)


_current_trace: ContextVar[ExecutionTrace | None] = ContextVar(
    "rpent_execution_trace", default=None
)


def _active_trace() -> ExecutionTrace | None:
    """Return the call trace, following the capture into worker threads.

    ``ToolCallCapture.bind`` already propagates through async tasks and
    ``to_thread`` workers. Reusing it here gives the write ledger the same
    propagation without a second binding mechanism.
    """
    trace = _current_trace.get()
    if trace is not None:
        return trace
    capture = current_tool_call.get()
    return getattr(capture, "execution_trace", None) if capture is not None else None


@contextmanager
def track_execution(episode_id: str | None = None) -> Iterator[ExecutionTrace]:
    """Collect the writes issued while executing one tool call."""
    trace = ExecutionTrace(episode_id=episode_id)
    capture = current_tool_call.get()
    if capture is not None:
        capture.execution_trace = trace
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        if capture is not None and capture.execution_trace is trace:
            capture.execution_trace = None
        _current_trace.reset(token)


def mark_write_issued(kind: str, *, request_id: str | None = None) -> None:
    """Record a write request before it is sent to the environment.

    Args:
        kind: Operation name, such as ``step`` or ``reset``.
        request_id: Transport request identity when the client has one.
    """
    trace = _active_trace()
    if trace is not None:
        trace.requests.append(
            WriteRequest(
                kind=kind,
                sequence=len(trace.requests),
                request_id=request_id,
            )
        )


def writes_issued() -> bool:
    """Whether the current tool call issued an environment write."""
    trace = _active_trace()
    return trace is not None and trace.issued


__all__ = [
    "ExecutionTrace",
    "WriteRequest",
    "mark_write_issued",
    "track_execution",
    "writes_issued",
]
