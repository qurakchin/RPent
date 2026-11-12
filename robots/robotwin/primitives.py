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

"""RoboTwin primitives built on RLinf environment APIs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from robots.robotwin.env_client import RoboTwinEnvClient
from robots.robotwin.vla_client import LingBotVLAClient
from robots.robotwin.wam_client import RoboTwinWAMClient
from rpent.tools import ToolResult, tool


class RoboTwinPrimitives:
    """Compose RoboTwin operations from the RLinf environment API."""

    def __init__(
        self,
        *,
        env: RoboTwinEnvClient,
        model: LingBotVLAClient | RoboTwinWAMClient,
        seed: int,
        check_cancelled: Callable[[], None],
        seed_mode: str = "exact",
        policy_kind: str = "vla",
    ):
        if seed_mode != "exact":
            raise ValueError("standard RoboTwin integration requires seed_mode='exact'")
        self.env = env
        self.model = model
        self.policy_kind = policy_kind
        self.seed = int(seed)
        self._check_cancelled = check_cancelled
        self.policy_actions = 0
        self.native_actions = 0
        self._recording = False
        self._frames: list[np.ndarray] = []

    def check_cancelled(self) -> None:
        """Raise when the current tool call has been interrupted."""
        self._check_cancelled()

    def recording_frames(self) -> bool:
        """Whether chunk execution should return every frame for the video."""
        return self._recording and (
            self.env.execution_capabilities.get("chunk_step_all_frames") is True
        )

    def start_recording(self) -> None:
        self._recording = True
        self._frames = []

    def record_frame(self, rgb: Any) -> None:
        self._frames.append(np.ascontiguousarray(np.asarray(rgb)))

    def recorded_frame_count(self) -> int:
        return len(self._frames)

    def stop_recording(self) -> list[np.ndarray]:
        frames = list(self._frames)
        self._recording = False
        self._frames = []
        return frames

    def frame_slice(self, start: int) -> list[np.ndarray]:
        return list(self._frames[int(start) :])

    def reset(
        self,
        *,
        instruction: str | None = None,
        feasibility_precheck: bool = True,
    ) -> dict[str, Any]:
        """Reset the RoboTwin episode and return the native info plus success."""
        del instruction, feasibility_precheck
        _, info = self.env.reset()
        if self.policy_kind == "wam":
            self.model.reset()
        return {**info, "success": True}

    @staticmethod
    def _completion(
        *, requested: int, executed: int, status: dict[str, Any]
    ) -> dict[str, Any]:
        step_lim = status.get("step_lim")
        budget_exhausted = step_lim is not None and int(
            status.get("take_action_cnt", 0)
        ) >= int(step_lim)
        completed = executed == requested
        if status.get("eval_success") is True:
            stop_reason = "native_success"
        elif budget_exhausted:
            stop_reason = "budget_exhausted"
        elif completed:
            stop_reason = "completed"
        else:
            stop_reason = "runtime_failure"
        return {
            "completed": completed,
            "requested_steps": requested,
            "executed_steps": executed,
            "stop_reason": stop_reason,
        }

    @staticmethod
    def _validate_qpos_updates_request(updates: Any) -> list[dict[str, Any]]:
        if not isinstance(updates, list) or not updates:
            raise ValueError("qpos updates must contain at least one update")
        normalized = []
        for update in updates:
            if not isinstance(update, dict):
                raise TypeError("qpos update must be a mapping")
            arm = update.get("arm")
            if arm not in ("left", "right"):
                raise ValueError("arm must be 'left' or 'right'")
            if update.get("arm_qpos") is None and update.get("gripper") is None:
                raise ValueError("qpos update must set arm_qpos and/or gripper")
            item: dict[str, Any] = {"arm": arm}
            if update.get("arm_qpos") is not None:
                arm_qpos = np.asarray(update["arm_qpos"], dtype=np.float64)
                if arm_qpos.shape != (6,) or not np.isfinite(arm_qpos).all():
                    raise ValueError("arm_qpos must be finite and have shape (6,)")
                item["arm_qpos"] = arm_qpos
            if update.get("gripper") is not None:
                gripper = float(update["gripper"])
                if not np.isfinite(gripper):
                    raise ValueError("gripper must be finite")
                item["gripper"] = gripper
            normalized.append(item)
        return normalized

    def apply_qpos_updates(
        self,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compose qpos waypoint actions from the latest robot state."""
        if self.env.terminated or self.env.truncated:
            raise RuntimeError("RoboTwin common episode is terminal; reset is required")
        updates = self._validate_qpos_updates_request(updates)
        executed = 0
        episode_status: dict[str, Any] | None = None
        for update in updates:
            state = self.env.last_info["robot_state"]
            qpos_target14 = np.asarray(state.get("qpos_target14"), dtype=np.float64)
            if qpos_target14.shape != (14,) or not np.isfinite(qpos_target14).all():
                raise ValueError(
                    "RoboTwin robot_state.qpos_target14 must be finite and have "
                    "shape (14,)"
                )
            action = qpos_target14.copy()
            offset = 0 if update["arm"] == "left" else 7
            if "arm_qpos" in update:
                action[offset : offset + 6] = update["arm_qpos"]
            if "gripper" in update:
                action[offset + 6] = update["gripper"]
            obs, _, _, _, info = self.env.step(action, action_type="qpos")
            if self._recording and isinstance(obs, dict) and "main_images" in obs:
                self.record_frame(obs["main_images"])
            executed += int(info.get("executed_actions", 0))
            episode_status = info["episode_status"]
            if self.env.terminated or self.env.truncated:
                break
        if episode_status is None:
            raise RuntimeError("RoboTwin qpos composition executed no updates")
        return {
            "action_type": "qpos",
            "requested_actions": len(updates),
            "executed_actions": executed,
            "episode_status": episode_status,
        }

    def execute_action(
        self, values: list[float], action_type: str | None = None
    ) -> ToolResult:
        """Execute one native qpos or end-effector waypoint."""
        if action_type is None:
            action_type = next(iter(self.env.action_specs))
        action = self.env.validate_action(values, action_type=action_type)
        self._check_cancelled()
        obs, _, _, _, info = self.env.step(action, action_type=action_type)
        if self._recording and isinstance(obs, dict) and "main_images" in obs:
            self.record_frame(obs["main_images"])
        executed = int(info.get("executed_actions", 0))
        self.native_actions += executed
        return ToolResult(
            data={
                **self._completion(
                    requested=1, executed=executed, status=info["episode_status"]
                ),
                "action_type": action_type,
                "episode_status": info["episode_status"],
            }
        )

    def status(self) -> dict[str, Any]:
        """Return the native episode status plus action counters."""
        return {
            **self.env.last_info["episode_status"],
            "policy_actions": self.policy_actions,
            "native_actions": self.native_actions,
        }

    @tool(readonly=True)
    def finish(self, *, status: str, summary: str) -> ToolResult:
        """Stop the run. A fresh native status query is authoritative; requesting success cannot override TASK_ENV.eval_success."""
        requested_success = status.lower() == "success"
        try:
            native = self.status()
        except Exception as error:  # The terminal tool must still stop the Planner.
            return ToolResult(
                data={
                    "_finish": True,
                    "status": "error",
                    "summary": summary,
                    "requested_status": status,
                    "requested_success": requested_success,
                    "runtime_error": f"{type(error).__name__}: {error}",
                }
            )
        verified_success = native.get("eval_success") is True
        reported_status = (
            "success"
            if verified_success
            else ("failure" if requested_success else status)
        )
        return ToolResult(
            data={
                "_finish": True,
                "status": reported_status,
                "summary": summary,
                "requested_success": requested_success,
                "success": verified_success,
                "episode_status": native,
            }
        )
