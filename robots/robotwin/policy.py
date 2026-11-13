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

"""Bind RoboTwin's VLA/WAM clients and env transport to the policy runner."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from robots.robotwin.primitives import RoboTwinPrimitives
from robots.robotwin.robot_spec import MODEL_SPEC, ROBOTWIN_CAMERA_NAMES
from rpent.session.env_capture import CapturingEnvClient


class RoboTwinPolicyBinding:
    """Expose one connected policy through ``PolicyBinding``."""

    def __init__(self, primitives: RoboTwinPrimitives) -> None:
        self._primitives = primitives
        self.kind = primitives.policy_kind
        self.backend = "wam" if self.kind == "wam" else "lingbot"
        self.tool_name = "wam_act" if self.kind == "wam" else "lingbot_act"
        self.model_name = "the selected WAM" if self.kind == "wam" else "LingBot-VLA"
        self.use_length = MODEL_SPEC.use_length if self.kind != "wam" else None
        self.action_type = primitives.model.action_type if self.kind == "wam" else "ee"

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


__all__ = ["RoboTwinPolicyBinding"]
