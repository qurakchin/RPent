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

"""LingBot's copy of the RoboTwin EEF16 runtime contract.

The robot slice owns ``RoboTwinModelSpec`` in ``robots/robotwin/contracts.py``;
a model service may not import a robot, so this module repeats the fields and
the runtime identity the server publishes. The drift test in
``tests/unit_tests/contracts/test_model_platforms`` keeps the two sides equal.
"""

from __future__ import annotations

LINGBOT_MODEL_SPEC = {
    "policy_name": "robotwin_eef",
    "robot_config_relpath": "configs/robot_configs/robotwin_eef.yaml",
    "norm_stats": "norm_stats/robotwin_eef.json",
    "qwen_base": "qwen_base",
    "camera_order": ("cam_high", "cam_left_wrist", "cam_right_wrist"),
    "state_layout": "eef16",
    "action_layout": "eef16",
    "use_length": 50,
}


def vla_runtime_contract() -> dict[str, object]:
    """Return the identity this server publishes for the robot's check."""
    return {
        "runtime": "lingbotvla",
        "policy_name": LINGBOT_MODEL_SPEC["policy_name"],
        "camera_order": list(LINGBOT_MODEL_SPEC["camera_order"]),
        "state_layout": LINGBOT_MODEL_SPEC["state_layout"],
        "action_layout": LINGBOT_MODEL_SPEC["action_layout"],
        "use_length": LINGBOT_MODEL_SPEC["use_length"],
    }
