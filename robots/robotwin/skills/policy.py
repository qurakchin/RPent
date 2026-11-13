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

"""RoboTwin VLA/WAM skill binding and its planner-facing declarations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from functools import partial
from typing import Annotated, Any

from pydantic import Field

from robots.robotwin.primitives import RoboTwinPrimitives
from robots.robotwin.robot_spec import MODEL_SPEC, ROBOTWIN_CAMERA_NAMES
from rpent.session.env_capture import CapturingEnvClient
from rpent.tools.base import Tool, ToolResult, tool
from rpent.tools.motion.vla_act import (
    SkillBinding,
    SkillConfig,
    limit_chunks,
    run_skill,
)


@tool(exclude=("binding",))
def lingbot_act(
    *,
    binding: SkillBinding,
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
    expected = binding.use_length
    if expected is not None and int(use_length) != expected:
        raise ValueError(f"{binding.model_name} requires use_length={expected}")
    return run_skill(
        binding,
        chunks=int(chunks),
        use_length=int(use_length),
        prompt=prompt,
        override_prompt=False,
    )


@tool(exclude=("binding",))
def wam_act(
    prompt: Annotated[str, Field(min_length=1)] | None = None,
    *,
    binding: SkillBinding,
    max_chunks: Annotated[int, Field(strict=True, ge=1, le=4)] = 1,
) -> ToolResult:
    """Execute bounded action chunks from the bound WAM on current observations. Omit prompt for the native task, or supply a subtask for this call. Inspect the resulting state before continuing; predictions do not establish task success.

    Args:
        prompt: Concrete instruction for this call; omit or null for the native task.
        max_chunks: One to four predictions before planner feedback (default 1).
    """
    chunks = limit_chunks(max_chunks, binding.max_chunks)
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
        raise ValueError("prompt must be a non-empty instruction or null")
    return run_skill(
        binding,
        chunks=chunks,
        use_length=None,
        prompt=prompt,
        override_prompt=True,
    )


def skill_declarations() -> tuple[Tool, ...]:
    """Return both RoboTwin skill declarations without a connected client."""
    return (lingbot_act, wam_act)


class RoboTwinSkillBinding:
    """Expose one connected RoboTwin policy through ``SkillBinding``."""

    def __init__(
        self,
        primitives: RoboTwinPrimitives,
        *,
        config: SkillConfig | None = None,
    ) -> None:
        self._primitives = primitives
        self.kind = primitives.policy_kind
        self.backend = "wam" if self.kind == "wam" else "lingbot"
        self.tool_name = "wam_act" if self.kind == "wam" else "lingbot_act"
        self.model_name = "the selected WAM" if self.kind == "wam" else "LingBot-VLA"
        self.use_length = MODEL_SPEC.use_length if self.kind != "wam" else None
        self.action_type = primitives.model.action_type if self.kind == "wam" else "ee"
        self._config = config or SkillConfig(use_length=self.use_length)

    @property
    def max_chunks(self) -> int:
        """Maximum prediction count this binding accepts per call."""
        return self._config.max_chunks

    def tools(self) -> Sequence[Tool]:
        """Return the declaration selected by the connected policy kind."""
        declaration = wam_act if self.kind == "wam" else lingbot_act
        return (declaration.with_handler(partial(declaration, binding=self)),)

    def check_cancelled(self) -> None:
        self._primitives.check_cancelled()

    def episode_status(self) -> Mapping[str, Any]:
        return self._primitives.env.last_info["episode_status"]

    def prediction(self, native_prompt: str) -> AbstractContextManager[Any]:
        env = self._primitives.env
        if isinstance(env, CapturingEnvClient):
            return env.prediction(native_prompt)
        return nullcontext()

    def observe(self, prompt: str | None) -> tuple[Mapping[str, Any], str]:
        observation: dict[str, Any] = {
            "views": {
                camera: {"rgb": self._primitives.env.render_camera(camera)}
                for camera in ROBOTWIN_CAMERA_NAMES
            },
            "robot_state": self._primitives.env.last_info["robot_state"],
            "task_language": self._primitives.env.get_task_language(),
        }
        if prompt is not None:
            observation["task_language"] = prompt
        native_prompt = str(observation["task_language"])
        return observation, native_prompt

    def predict(self, observation: Mapping[str, Any]) -> Sequence[Any]:
        model = self._primitives.model
        if self.kind == "wam":
            return model.predict(observation)
        return model.infer(observation)

    def execute(self, actions: Sequence[Any]) -> int:
        primitives = self._primitives
        env = primitives.env
        payload, _, _, _, info = env.chunk_step(
            actions,
            action_type=self.action_type,
            return_all_frames=primitives.recording_frames(),
        )
        if isinstance(payload, dict) and "frames" in payload:
            for frame in payload["frames"]:
                primitives.record_frame(frame["observation"]["head_camera"]["rgb"])
        executed = int(info.get("executed_actions", 0))
        primitives.policy_actions += executed
        primitives.native_actions += executed
        return executed


__all__ = [
    "RoboTwinSkillBinding",
    "lingbot_act",
    "skill_declarations",
    "wam_act",
]
