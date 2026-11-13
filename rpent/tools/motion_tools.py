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

"""Motion family: waypoint interpolation and uniform stop feedback.

The shared executor owns scaling, convergence checks, and the feedback
contract. A backend supplies the platform's path planner and action transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Mapping, Protocol, Sequence

import numpy as np
from pydantic import Field

from rpent.tools.base import Tool, ToolResult, iter_tools, tool
from rpent.tools.capabilities import Capabilities, ToolFamily
from rpent.utils.logging import get_logger

logger = get_logger("tools.motion")


class MotionBackend(Protocol):
    """Platform operations the shared motion executor depends on."""

    def check_cancelled(self) -> None:
        """Raise at a safe cancellation boundary."""

    def robot_state(self) -> Mapping[str, Any]:
        """Return current EEF poses and gripper values."""

    def episode_status(self) -> Mapping[str, Any]:
        """Return native success and step-budget counters."""

    def plan_arm_path(self, arm: str, target: Sequence[float]) -> Mapping[str, Any]:
        """Plan qpos waypoints for one arm toward a world pose."""

    def apply_qpos_updates(self, updates: list[dict[str, Any]]) -> Mapping[str, Any]:
        """Execute qpos or gripper updates with fresh state per waypoint."""

    def account_native_actions(self, count: int) -> None:
        """Record executed native actions for run metrics."""


@dataclass(frozen=True)
class MotionConfig:
    """Convergence tolerances and the commanded-path safety limit.

    ``max_waypoint_jump_m`` rejects a plan whose adjacent Cartesian waypoints
    are farther apart than one native step should ever move the arm. It guards
    the command before execution; a slice that needs a looser bound sets it in
    its own config.
    """

    position_tolerance_m: float = 0.01
    orientation_tolerance_rad: float = 0.05
    gripper_tolerance: float = 0.02
    max_waypoint_jump_m: float = 0.5


def _qmult(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = left
    w2, x2, y2, z2 = right
    return np.asarray(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=np.float64,
    )


def quaternion_angle(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the shortest rotation angle between two wxyz quaternions."""
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    left_norm = np.linalg.norm(left_array)
    right_norm = np.linalg.norm(right_array)
    if left_norm == 0 or right_norm == 0:
        return float("nan")
    dot = abs(float(np.dot(left_array, right_array)) / (left_norm * right_norm))
    return float(2.0 * np.arccos(np.clip(dot, -1.0, 1.0)))


def stop_reason(
    *,
    requested: int,
    executed: int,
    status: Mapping[str, Any],
    reached: bool | None = None,
    diverged: bool | None = None,
    unsafe: bool | None = None,
) -> str:
    """Map native counters and convergence to the shared stop vocabulary."""
    if unsafe is True:
        return "unsafe_motion"
    if status.get("eval_success") is True:
        return "episode_over"
    step_lim = status.get("step_lim")
    if step_lim is not None and int(status.get("take_action_cnt", 0)) >= int(step_lim):
        return "max_steps"
    if executed == 0 or executed < requested:
        return "stalled"
    if diverged is True:
        return "diverging"
    if reached is True:
        return "arrived"
    return "max_steps"


def _execution_layer(requested: int, executed: int) -> tuple[str, bool]:
    """Return ``(execution_status, no_execution)`` for native counters."""
    if executed == 0:
        return "not_started", True
    if executed < requested:
        return "partial", False
    return "completed", False


def _stop_evidence(
    *,
    requested: int,
    executed: int,
    status: Mapping[str, Any],
    position_error: float | None = None,
    initial_position_error: float | None = None,
    max_waypoint_jump_m: float | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "requested_steps": requested,
        "executed_steps": executed,
    }
    for key in ("step_lim", "take_action_cnt", "eval_success"):
        if key in status:
            evidence[key] = status[key]
    if max_waypoint_jump_m is not None:
        evidence["max_waypoint_jump_m"] = max_waypoint_jump_m
    if initial_position_error is not None:
        evidence["initial_position_error_m"] = initial_position_error
    if position_error is not None:
        evidence["final_position_error_m"] = position_error
        if initial_position_error is not None:
            evidence["window_improvement_m"] = (
                initial_position_error - position_error
            )
    return evidence


class MotionTools(ToolFamily):
    """Shared tool declarations backed by one :class:`MotionBackend`."""

    name = "motion"

    def __init__(
        self,
        backend: MotionBackend,
        *,
        config: MotionConfig | None = None,
    ) -> None:
        self._backend = backend
        self._config = config or MotionConfig()

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        if capabilities is not None and not capabilities.supports_execution(
            "step", "chunk_step"
        ):
            # A declared host that cannot step or chunk cannot move either.
            logger.info(
                "motion tools omitted: nothing declares step or chunk_step "
                "(execution=%s)",
                dict(capabilities.execution),
            )
            return ()
        return tuple(iter_tools(self))

    def _feedback(
        self,
        *,
        requested: int,
        executed: int,
        status: Mapping[str, Any],
        position_error: float | None = None,
        orientation_error: float | None = None,
        reached: bool | None = None,
        diverged: bool | None = None,
        unsafe: bool | None = None,
        initial_position_error: float | None = None,
        max_waypoint_jump_m: float | None = None,
        stop_reason_override: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "completed": requested > 0 and executed == requested,
            "requested_steps": requested,
            "executed_steps": executed,
            "stop_reason": stop_reason_override
            or stop_reason(
                requested=requested,
                executed=executed,
                status=status,
                reached=reached,
                diverged=diverged,
                unsafe=unsafe,
            ),
            "stop_evidence": _stop_evidence(
                requested=requested,
                executed=executed,
                status=status,
                position_error=position_error,
                initial_position_error=initial_position_error,
                max_waypoint_jump_m=max_waypoint_jump_m,
            ),
            "pose_error": {
                "pos_m": position_error,
                "ori_rad": orientation_error,
            },
            "episode_status": dict(status),
            **extra,
        }

    @tool
    def move_to(
        self,
        *,
        arm: Literal["left", "right"],
        xyz: Annotated[list[float], Field(min_length=3, max_length=3)],
        quat: Annotated[list[float], Field(min_length=4, max_length=4)] | None = None,
        gripper: float | None = None,
        substeps: Annotated[int, Field(ge=0, json_schema_extra={"default": 25})] = 25,
    ) -> ToolResult:
        """Plan and move one arm to a world-frame xyz and optional wxyz orientation. Reports pose_error and a stop_reason; completed means the waypoints ran, not that the grasp succeeded.

        Args:
            arm: Arm to move.
            xyz: Target world position in metres.
            quat: Target wxyz orientation; default keeps the current orientation.
            gripper: Optional normalized gripper command applied along the path.
            substeps: Waypoints to execute; 0 keeps the whole planned path.
        """
        if int(substeps) < 0:
            raise ValueError("substeps must be non-negative")
        backend = self._backend
        backend.check_cancelled()
        state = backend.robot_state()
        key = f"{arm}_eef_pose"
        pose = np.asarray(state[key], dtype=np.float64)
        if pose.shape != (7,):
            raise ValueError(f"{key} must have shape (7,)")
        if quat is None:
            quat = pose[3:].tolist()
        target = np.asarray([*xyz, *quat], dtype=np.float64)
        target_xyz = np.asarray(xyz, dtype=np.float64)
        initial_position_error = float(np.linalg.norm(pose[:3] - target_xyz))
        planned = backend.plan_arm_path(arm, target)
        backend.check_cancelled()
        if planned.get("status") != "Success" or planned.get("position") is None:
            current = pose[:3]
            return ToolResult(
                data=self._feedback(
                    requested=0,
                    executed=0,
                    status=backend.episode_status(),
                    position_error=float(np.linalg.norm(current - target_xyz)),
                    orientation_error=quaternion_angle(pose[3:], quat),
                    reached=False,
                    initial_position_error=initial_position_error,
                    stop_reason_override="planning_rejected",
                    plan_status=planned.get("status"),
                    hint="target may be unreachable or in collision",
                ),
                no_execution=True,
                execution_status="rejected",
            )
        path = np.asarray(planned["position"], dtype=np.float64)
        substeps = int(substeps)
        if substeps == 1:
            path = path[-1:]
        elif substeps >= 2 and len(path) > substeps:
            indices = np.linspace(0, len(path) - 1, substeps).astype(int)
            path = path[indices]
        max_waypoint_jump = (
            float(np.max(np.linalg.norm(np.diff(path[:, :3], axis=0), axis=1)))
            if len(path) > 1
            else 0.0
        )
        if (
            self._config.max_waypoint_jump_m is not None
            and max_waypoint_jump > self._config.max_waypoint_jump_m
        ):
            return ToolResult(
                data=self._feedback(
                    requested=0,
                    executed=0,
                    status=backend.episode_status(),
                    position_error=initial_position_error,
                    orientation_error=quaternion_angle(pose[3:], quat),
                    reached=False,
                    unsafe=True,
                    initial_position_error=initial_position_error,
                    max_waypoint_jump_m=max_waypoint_jump,
                    hint=(
                        "planned waypoints jump farther than "
                        f"{self._config.max_waypoint_jump_m} m; adjust the target"
                    ),
                ),
                no_execution=True,
                execution_status="rejected",
            )
        updates = [
            {"arm": arm, "arm_qpos": waypoint, "gripper": gripper} for waypoint in path
        ]
        execution = backend.apply_qpos_updates(updates)
        executed = int(execution.get("executed_actions", 0))
        backend.account_native_actions(executed)
        backend.check_cancelled()
        status = execution.get("episode_status") or backend.episode_status()
        final = np.asarray(backend.robot_state()[key], dtype=np.float64)
        position_error = float(np.linalg.norm(final[:3] - target_xyz))
        orientation_error = quaternion_angle(final[3:], quat)
        reached = (
            position_error <= self._config.position_tolerance_m
            and orientation_error <= self._config.orientation_tolerance_rad
        )
        diverged = not reached and position_error > initial_position_error
        execution_status, no_execution = _execution_layer(len(updates), executed)
        return ToolResult(
            data=self._feedback(
                requested=len(updates),
                executed=executed,
                status=status,
                position_error=position_error,
                orientation_error=orientation_error,
                reached=reached,
                diverged=diverged,
                initial_position_error=initial_position_error,
                max_waypoint_jump_m=max_waypoint_jump,
                plan_status=planned.get("status"),
                waypoints=len(path),
                final_eef_xyz=final[:3].tolist(),
            ),
            no_execution=no_execution,
            execution_status=execution_status,
        )

    @tool
    def rotate_wrist(
        self,
        *,
        arm: Literal["left", "right"],
        delta_yaw_deg: float,
        gripper: float | None = None,
        substeps: Annotated[int, Field(ge=0, json_schema_extra={"default": 25})] = 25,
    ) -> ToolResult:
        """Rotate one end effector about world Z by a relative angle in degrees.

        Args:
            arm: Arm to rotate.
            delta_yaw_deg: Relative world-Z rotation in degrees.
            gripper: Optional normalized gripper command applied along the path.
            substeps: Waypoints to execute; 0 keeps the whole planned path.
        """
        pose = np.asarray(
            self._backend.robot_state()[f"{arm}_eef_pose"], dtype=np.float64
        )
        yaw = np.deg2rad(float(delta_yaw_deg))
        world_z = np.asarray([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])
        result = self.move_to(
            arm=arm,
            xyz=pose[:3].tolist(),
            quat=_qmult(world_z, pose[3:]).tolist(),
            gripper=gripper,
            substeps=substeps,
        )
        result.data["requested_delta_yaw_deg"] = float(delta_yaw_deg)
        return result

    @tool
    def set_gripper(
        self,
        *,
        arm: Literal["left", "right"],
        val: Annotated[float, Field(ge=0, le=1)],
        steps: Annotated[int, Field(ge=1, json_schema_extra={"default": 10})] = 10,
    ) -> ToolResult:
        """Move one normalized gripper to val through interpolated native actions.

        Args:
            arm: Arm whose gripper moves.
            val: Normalized target from 0 (closed) to 1 (open).
            steps: Interpolated actions before returning feedback.
        """
        if int(steps) < 1:
            raise ValueError("steps must be at least 1")
        backend = self._backend
        backend.check_cancelled()
        current = float(backend.robot_state()[f"{arm}_gripper"])
        step_count = int(steps)
        target = float(val)
        initial_error = abs(current - target)
        values = [
            current + (target - current) * index / step_count
            for index in range(1, step_count + 1)
        ]
        updates = [{"arm": arm, "gripper": float(value)} for value in values]
        execution = backend.apply_qpos_updates(updates)
        executed = int(execution.get("executed_actions", 0))
        backend.account_native_actions(executed)
        backend.check_cancelled()
        status = execution.get("episode_status") or backend.episode_status()
        gripper_val = float(backend.robot_state()[f"{arm}_gripper"])
        error = abs(gripper_val - target)
        reached = error <= self._config.gripper_tolerance
        diverged = not reached and error > initial_error
        execution_status, no_execution = _execution_layer(len(updates), executed)
        return ToolResult(
            data=self._feedback(
                requested=len(updates),
                executed=executed,
                status=status,
                reached=reached,
                diverged=diverged,
                gripper_val=gripper_val,
                target_gripper_val=target,
                gripper_error=error,
                initial_gripper_error=initial_error,
            ),
            no_execution=no_execution,
            execution_status=execution_status,
        )

    @tool
    def release(
        self,
        *,
        arm: Literal["left", "right"],
        val: Annotated[float, Field(json_schema_extra={"default": 1.0})] = 1.0,
        steps: Annotated[int, Field(ge=1, json_schema_extra={"default": 10})] = 10,
    ) -> ToolResult:
        """Open one gripper, by default to 1.0, through interpolated native actions.

        Args:
            arm: Arm whose gripper opens.
            val: Normalized target from 0 (closed) to 1 (open).
            steps: Interpolated actions before returning feedback.
        """
        return self.set_gripper(arm=arm, val=val, steps=steps)


__all__ = ["MotionBackend", "MotionConfig", "MotionTools", "quaternion_angle"]
