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

"""RoboTwin wire contracts used by the UniWAM adapter.

A model service may not import a robot slice, so it keeps its own copies of
the native action layout and camera roles. The platform contract test keeps
them equal to ``robots/robotwin/``.
"""

from __future__ import annotations

from rpent.models.contracts import AMControlSpec

# Native joint_action.vector order: left six joint targets and gripper,
# then right six joint targets and gripper. Preserve native gripper values.
ROBOTWIN_QPOS = AMControlSpec(
    embodiment="robotwin_qpos14",
    action_space="robotwin.joint_action.qpos14.v1",
    action_schema=[f"joint_action_{i}" for i in range(14)],
    action_type="qpos",
)

# Camera roles RoboTwin exposes, in the order model adapters expect.
ROBOTWIN_CAMERAS = ("head", "left_wrist", "right_wrist")
