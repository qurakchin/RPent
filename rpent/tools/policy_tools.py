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

"""Policy family: the single runner for VLA/WAM client skills.

A binding owns the model client and action transport. The runner owns chunk
looping, budget checks, cancellation, and the feedback contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from pydantic import Field

from rpent.tools.base import Tool, ToolResult, iter_tools, tool
from rpent.tools.capabilities import Capabilities, ToolFamily
from rpent.tools.motion_tools import stop_reason


class PolicyBinding(Protocol):
    """A connected client policy and the environment it acts on."""

    tool_name: str
    backend: str
    model_name: str
    action_type: str

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
class PolicyConfig:
    """Bounds for one client-policy call."""

    max_chunks: int = 4
    default_chunks: int = 4
    use_length: int | None = None


class PolicyTools(ToolFamily):
    """VLA/WAM tools backed by one :class:`PolicyBinding`."""

    name = "policy"

    def __init__(
        self,
        binding: PolicyBinding,
        *,
        config: PolicyConfig | None = None,
    ) -> None:
        self._binding = binding
        self._config = config or PolicyConfig()

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        if (
            capabilities is not None
            and capabilities.policy_backends
            and self._binding.backend not in capabilities.policy_backends
        ):
            return ()
        declarations = {
            declaration.name: declaration for declaration in iter_tools(self)
        }
        try:
            declaration = declarations[self._binding.tool_name]
        except KeyError as exc:
            raise ValueError(
                f"policy binding exposes unsupported tool {self._binding.tool_name!r}; "
                f"expected one of {sorted(declarations)}"
            ) from exc
        return (declaration,)

    def _limit(self, value: int) -> int:
        if type(value) is not int or not 1 <= value <= self._config.max_chunks:
            raise ValueError(
                f"chunks must be an integer between 1 and {self._config.max_chunks}"
            )
        return value

    def _run(
        self,
        *,
        chunks: int,
        use_length: int | None,
        prompt: str | None,
        override_prompt: bool,
    ) -> ToolResult:
        binding = self._binding
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
        reached = executed == requested
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
            }
        )

    @tool
    def lingbot_act(
        self,
        *,
        chunks: Annotated[int, Field(ge=1, json_schema_extra={"default": 4})] = 4,
        use_length: Annotated[
            int, Field(json_schema_extra={"default": 50, "const": 50})
        ] = 50,
        prompt: str | None = None,
    ) -> ToolResult:
        """Run the bound VLA policy with its native task instruction. The optional prompt is recorded but never sent to the policy.

        Args:
            chunks: Number of predictions to execute before returning feedback.
            use_length: Native action count per prediction; fixed by the model.
            prompt: Recorded observation about this call; not sent to the policy.
        """
        if int(chunks) < 1:
            raise ValueError("chunks must be at least 1")
        expected = self._config.use_length
        if expected is not None and int(use_length) != expected:
            raise ValueError(
                f"{self._binding.model_name} requires use_length={expected}"
            )
        return self._run(
            chunks=int(chunks),
            use_length=int(use_length),
            prompt=prompt,
            override_prompt=False,
        )

    @tool
    def wam_act(
        self,
        prompt: Annotated[str, Field(min_length=1)] | None = None,
        *,
        max_chunks: Annotated[int, Field(strict=True, ge=1, le=4)] = 1,
    ) -> ToolResult:
        """Execute bounded action chunks from the bound WAM on current observations. Omit prompt for the native task, or supply a subtask for this call. Inspect the resulting state before continuing; predictions do not establish task success.

        Args:
            prompt: Concrete instruction for this call; omit or null for the native task.
            max_chunks: One to four predictions before planner feedback (default 1).
        """
        chunks = self._limit(max_chunks)
        if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
            raise ValueError("prompt must be a non-empty instruction or null")
        return self._run(
            chunks=chunks,
            use_length=None,
            prompt=prompt,
            override_prompt=True,
        )


__all__ = ["PolicyBinding", "PolicyConfig", "PolicyTools"]
