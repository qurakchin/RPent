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

"""RoboTwin's runtime contract, shared by the simulator, robots, and models.

The simulator owns these values: its environment server and the robot adapter
that drives it must agree on the task list, camera order, and action layout,
and the LingBot component keeps a copy in
``components/models/lingbot/contracts.py`` because a model service may not
import a simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from components.sim.robotwin.observation import ROBOTWIN_CAMERAS

# Native RoboTwin task YAMLs exposed to the dashboard, the CLI, and the env
# server -- defined once so every consumer shows the same choices.
ROBOTWIN_TASK_CONFIGS = (
    "demo_clean",
    "demo_randomized",
)

#: Env-side camera names exposed by the RoboTwin EnvServer, in fixed order.
#: Shared across the env client, primitives, and toolkit.
ROBOTWIN_CAMERA_NAMES = ROBOTWIN_CAMERAS

#: Supported native action representations for the RoboTwin agent runtime.
RoboTwinActionType = Literal["qpos", "ee"]


@dataclass(frozen=True)
class RoboTwinModelSpec:
    """Values required by the LingBot EEF runtime."""

    policy_name: str
    robot_config_relpath: str
    norm_stats: str
    qwen_base: str
    camera_order: tuple[str, ...]
    state_layout: str
    action_layout: str
    use_length: int


MODEL_SPEC = RoboTwinModelSpec(
    policy_name="robotwin_eef",
    robot_config_relpath="configs/robot_configs/robotwin_eef.yaml",
    norm_stats="norm_stats/robotwin_eef.json",
    qwen_base="qwen_base",
    camera_order=("cam_high", "cam_left_wrist", "cam_right_wrist"),
    state_layout="eef16",
    action_layout="eef16",
    use_length=50,
)


def vla_runtime_contract() -> dict[str, object]:
    """Return the identity required from a LingBot RoboTwin server.

    Only the hard contract fields that break inference input/output when
    mismatched are kept; descriptive behaviour fields live with the
    implementation (facade/transport), not in the runtime-equality check.
    """
    return {
        "runtime": "lingbotvla",
        "policy_name": MODEL_SPEC.policy_name,
        "camera_order": list(MODEL_SPEC.camera_order),
        "state_layout": MODEL_SPEC.state_layout,
        "action_layout": MODEL_SPEC.action_layout,
        "use_length": MODEL_SPEC.use_length,
    }


def env_runtime_contract(
    *,
    task_name: str,
    task_config: str,
    seed: int,
    max_episode_steps: int = 10000,
) -> dict[str, object]:
    """Return the identity required from a RoboTwin EnvServer."""
    return {
        "runtime": "rlinf_robotwin_env",
        "task_name": task_name,
        "task_config": task_config,
        "seed": int(seed),
        "seed_mode": "exact",
        "action_layouts": ["qpos14", MODEL_SPEC.action_layout],
        "execution": {
            "reset": True,
            "step": True,
            "chunk_step": True,
            "action_layouts": ["qpos14", MODEL_SPEC.action_layout],
            "chunk_step_all_frames": True,
            "chunk_step_frame_format": "robotwin.observation",
            "step_limit": int(max_episode_steps),
        },
        "extensions": {
            "render_camera": {
                "camera_names": list(ROBOTWIN_CAMERA_NAMES),
                "metric_depth": True,
            },
            "get_camera_meta": True,
            "get_task_language": True,
            "plan_arm_path": True,
        },
    }
