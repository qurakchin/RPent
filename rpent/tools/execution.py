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


@dataclass
class ExecutionTrace:
    """State-changing requests issued by one tool call."""

    writes: list[str] = field(default_factory=list)

    @property
    def issued(self) -> bool:
        """Whether any environment write has been issued."""
        return bool(self.writes)


_current_trace: ContextVar[ExecutionTrace | None] = ContextVar(
    "rpent_execution_trace", default=None
)


@contextmanager
def track_execution() -> Iterator[ExecutionTrace]:
    """Collect the writes issued while executing one tool call."""
    trace = ExecutionTrace()
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


def mark_write_issued(kind: str) -> None:
    """Record a write request before it is sent to the environment.

    Args:
        kind: Operation name, such as ``step`` or ``reset``.
    """
    trace = _current_trace.get()
    if trace is not None:
        trace.writes.append(kind)


def writes_issued() -> bool:
    """Whether the current tool call issued an environment write."""
    trace = _current_trace.get()
    return trace is not None and trace.issued


__all__ = ["ExecutionTrace", "mark_write_issued", "track_execution", "writes_issued"]
