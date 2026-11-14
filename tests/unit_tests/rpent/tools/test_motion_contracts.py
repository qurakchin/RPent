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

"""Motion feedback and execution layers for the shared executor."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from rpent.tools.motion_tools import MotionConfig, MotionTools

POSE = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
STATUS = {"eval_success": False, "take_action_cnt": 1, "step_lim": 100}


def _waypoint(x: float, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [x, y, z, 1.0, 0.0, 0.0, 0.0]


def _qpos(x: float) -> list[float]:
    """A six-joint waypoint, the shape the planner executes as qpos."""
    return [x, 0.0, 0.0, 0.0, 0.0, 0.0]


class _Backend:
    """Minimal transport with one plan, one execution, and two observations."""

    def __init__(
        self,
        *,
        plan: Mapping[str, Any],
        final_pose: Sequence[float],
        executed: int,
        status: Mapping[str, Any] = STATUS,
    ) -> None:
        self.plan = plan
        self.final_pose = final_pose
        self.executed = executed
        self.status = status
        self.state_calls = 0
        self.updates: list[dict[str, Any]] = []

    def check_cancelled(self) -> None:
        return None

    def robot_state(self) -> Mapping[str, Any]:
        self.state_calls += 1
        pose = POSE if self.state_calls == 1 else self.final_pose
        return {"left_eef_pose": pose, "left_gripper": 0.0}

    def episode_status(self) -> Mapping[str, Any]:
        return self.status

    def plan_arm_path(self, arm: str, target: Sequence[float]) -> Mapping[str, Any]:
        return self.plan

    def apply_qpos_updates(self, updates: list[dict[str, Any]]) -> Mapping[str, Any]:
        self.updates = updates
        return {"executed_actions": self.executed, "episode_status": self.status}

    def account_native_actions(self, count: int) -> None:
        return None


def _tools() -> MotionTools:
    return MotionTools(
        _Backend(plan={"status": "Failure"}, final_pose=POSE, executed=0),
        config=MotionConfig(),
    )


def test_planning_rejection_is_not_a_completed_execution() -> None:
    backend = _Backend(plan={"status": "Failure"}, final_pose=POSE, executed=0)
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.call_ok is True
    assert result.no_execution is True
    assert result.execution_status == "rejected"
    assert result.data["stop_reason"] == "planning_rejected"
    assert result.data["executed_steps"] == 0
    assert backend.updates == []


def test_partial_execution_reports_the_executed_step_count() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.0), _qpos(0.1)]},
        final_pose=_waypoint(0.05),
        executed=1,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.no_execution is False
    assert result.execution_status == "partial"
    assert result.data["stop_reason"] == "stalled"
    assert result.data["executed_steps"] == 1
    assert result.data["requested_steps"] == 2


def test_executed_path_that_did_not_converge_is_stalled() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.1)]},
        final_pose=_waypoint(0.05),
        executed=1,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.execution_status == "completed"
    assert result.data["completed"] is True
    assert result.data["stop_reason"] == "stalled"
    assert result.data["stop_evidence"]["final_position_error_m"] == 0.05


def test_divergence_wins_over_a_partial_path() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.0), _qpos(0.1)]},
        final_pose=_waypoint(-0.1),
        executed=1,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.execution_status == "partial"
    assert result.data["stop_reason"] == "diverging"
    assert result.data["stop_evidence"]["window_improvement_m"] < 0


def test_max_steps_requires_an_exhausted_native_budget() -> None:
    exhausted = {"eval_success": False, "take_action_cnt": 100, "step_lim": 100}
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.1)]},
        final_pose=_waypoint(0.1),
        executed=1,
        status=exhausted,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.data["stop_reason"] == "max_steps"
    assert result.data["stop_evidence"]["take_action_cnt"] == 100


def test_motion_that_increases_the_error_is_diverging() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.1)]},
        final_pose=_waypoint(-0.1),
        executed=1,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.execution_status == "completed"
    assert result.data["stop_reason"] == "diverging"
    evidence = result.data["stop_evidence"]
    assert evidence["window_improvement_m"] < 0
    assert evidence["initial_position_error_m"] == 0.1
    assert evidence["final_position_error_m"] == 0.2


def test_a_commanded_waypoint_jump_is_refused_before_execution() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.0), _qpos(0.9)]},
        final_pose=_waypoint(0.9),
        executed=2,
    )
    tools = MotionTools(backend, config=MotionConfig(max_waypoint_jump_rad=0.5))

    result = tools.move_to(arm="left", xyz=[0.9, 0.0, 0.0])

    assert result.no_execution is True
    assert result.execution_status == "rejected"
    assert result.data["stop_reason"] == "unsafe_motion"
    assert result.data["stop_evidence"]["max_waypoint_jump_rad"] == 0.9
    assert backend.updates == []


def test_arrival_reports_completed() -> None:
    backend = _Backend(
        plan={"status": "Success", "position": [_qpos(0.1)]},
        final_pose=_waypoint(0.1),
        executed=1,
    )
    tools = MotionTools(backend, config=MotionConfig())

    result = tools.move_to(arm="left", xyz=[0.1, 0.0, 0.0])

    assert result.execution_status == "completed"
    assert result.data["stop_reason"] == "arrived"
    assert result.data["completed"] is True


def test_motion_family_logs_omitted_tools(caplog) -> None:
    from rpent.tools.capabilities import Capabilities

    family = _tools()
    with caplog.at_level("INFO", logger="rpent.tools.motion"):
        assert family.tools(Capabilities(execution={})) == ()

    assert "motion tools omitted" in caplog.text
