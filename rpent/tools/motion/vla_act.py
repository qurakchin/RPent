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

"""Skill family: the single runner for VLA/WAM client skills.

A skill binding owns the model client, the action transport, and the
planner-facing declaration (tool name and schema). The runner owns chunk
looping, budget checks, cancellation, and the feedback contract. The binding
lives in ``robots/<name>/skills/<skill>.py``; this module never imports a robot
and contains no backend names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from rpent.tools.base import Tool, ToolResult
from rpent.tools.capabilities import Capabilities, ToolFamily
from rpent.tools.motion_tools import _execution_layer, stop_reason
from rpent.utils.logging import get_logger

logger = get_logger("tools.skill")


class SkillBinding(Protocol):
    """A connected client policy and the environment it acts on."""

    tool_name: str
    backend: str
    model_name: str
    action_type: str
    use_length: int | None
    max_chunks: int

    def tools(self) -> Sequence[Tool]:
        """Return this binding's planner-facing declarations."""

    def check_cancelled(self) -> None:
        """Raise at a safe cancellation boundary."""

    def episode_status(self) -> Mapping[str, Any]:
        """Return native success and step-budget counters."""

    def observe(self, prompt: str | None) -> tuple[Mapping[str, Any], str]:
        """Build the model observation and return it with the native prompt."""

    def prediction(self, native_prompt: str) -> AbstractContextManager[Any]:
        """Group the actions from one prediction under the native prompt."""

    def predict(self, observation: Mapping[str, Any]) -> Sequence[Any]:
        """Return one action chunk for the observation."""

    def execute(self, actions: Sequence[Any]) -> int:
        """Execute one chunk and return the number of executed actions."""


@dataclass(frozen=True)
class SkillConfig:
    """Bounds for one client-skill call."""

    max_chunks: int = 4
    use_length: int | None = None


def limit_chunks(value: int, maximum: int) -> int:
    """Validate a chunk budget without accepting bools or out-of-range values."""
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"chunks must be an integer between 1 and {maximum}")
    return value


def run_skill(
    binding: SkillBinding,
    *,
    chunks: int,
    use_length: int | None,
    prompt: str | None,
    override_prompt: bool,
) -> ToolResult:
    """Run bounded prediction/execution chunks and report execution truth."""
    executed = 0
    requested = chunks * use_length if use_length is not None else 0
    native_prompt = ""
    for _ in range(chunks):
        binding.check_cancelled()
        status = binding.episode_status()
        if status.get("eval_success") is True:
            break
        step_lim = status.get("step_lim")
        if step_lim is not None and int(status.get("take_action_cnt", 0)) >= int(
            step_lim
        ):
            break
        observation, native_prompt = binding.observe(
            prompt if override_prompt else None
        )
        with binding.prediction(native_prompt):
            actions = binding.predict(observation)
            if use_length is not None:
                actions = actions[:use_length]
            else:
                requested += len(actions)
            binding.check_cancelled()
            executed += int(binding.execute(actions))
        binding.check_cancelled()
    status = binding.episode_status()
    reached = requested > 0 and executed == requested
    execution_status, no_execution = _execution_layer(requested, executed)
    return ToolResult(
        data={
            "completed": reached,
            "requested_steps": requested,
            "executed_steps": executed,
            "stop_reason": stop_reason(
                requested=requested,
                executed=executed,
                status=status,
                reached=reached,
            ),
            "stop_evidence": {
                "requested_steps": requested,
                "executed_steps": executed,
                "step_lim": status.get("step_lim"),
                "take_action_cnt": status.get("take_action_cnt"),
            },
            "prompt": native_prompt,
            "agent_prompt_ignored": prompt is not None and not override_prompt,
            "ignored_agent_prompt": prompt if not override_prompt else None,
            "episode_status": dict(status),
        },
        no_execution=no_execution,
        execution_status=execution_status,
    )


class SkillTools(ToolFamily):
    """Publish the declaration owned by one :class:`SkillBinding`."""

    name = "skill"

    def __init__(self, binding: SkillBinding) -> None:
        self._binding = binding

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        if (
            capabilities is not None
            and self._binding.backend not in capabilities.policy_backends
        ):
            # Declared capabilities are authoritative: an undeclared backend
            # has no tool, even if the binding object exists.
            logger.warning(
                "skill tool omitted: connected backend %r is not declared in "
                "policy_backends=%s",
                self._binding.backend,
                list(capabilities.policy_backends),
            )
            return ()
        declarations = {
            declaration.name: declaration for declaration in self._binding.tools()
        }
        try:
            declaration = declarations[self._binding.tool_name]
        except KeyError as exc:
            raise ValueError(
                f"skill binding exposes unsupported tool {self._binding.tool_name!r}; "
                f"expected one of {sorted(declarations)}"
            ) from exc
        return (declaration,)


__all__ = ["SkillBinding", "SkillConfig", "SkillTools", "limit_chunks", "run_skill"]
