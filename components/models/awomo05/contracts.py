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

"""Awomo05's copy of the RoboDojo wire contract.

The robot slice owns the canonical values in ``robots/robodojo/access.py``; a
model service may not import a robot, so this module repeats the camera order,
joint layout and RGB check. ``tests/unit_tests/contracts/test_model_platforms``
keeps the two sides equal.
"""

from __future__ import annotations

import numpy as np

CAMERAS = ("cam_head", "cam_left_wrist", "cam_right_wrist")
ARX_X5_JOINT_FIELDS = {
    "left_arm_joint_state": 6,
    "left_ee_joint_state": 1,
    "right_arm_joint_state": 6,
    "right_ee_joint_state": 1,
}


def validate_rgb(obs: dict) -> None:
    """Require nonempty HWC uint8 RGB images from the head and wrist cameras."""
    for name in CAMERAS:
        rgb = np.asarray(obs.get("vision", {}).get(name, {}).get("color"))
        if (
            rgb.ndim != 3
            or rgb.shape[-1] != 3
            or min(rgb.shape[:2]) == 0
            or rgb.dtype != np.uint8
        ):
            raise ValueError(f"RoboDojo observation requires HWC uint8 RGB: {name}")
