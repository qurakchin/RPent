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

"""LIBERO's native OSC action layout shared by clients and model adapters."""

from rpent.models.contracts import AMControlSpec

# Values use LIBERO's native OSC scaling and gripper convention. Model
# adapters restore this representation before handing actions to the env.
# The model-side copies in ``components/models/{cosmos3,cosmos_policy,
# fast_wam}/platforms.py`` state what each adapter expects; keep them equal.
LIBERO_OSC = AMControlSpec(
    embodiment="libero_7d",
    action_space="libero.osc_pose.delta.v1",
    action_schema=[
        "delta_x",
        "delta_y",
        "delta_z",
        "delta_axis_angle_x",
        "delta_axis_angle_y",
        "delta_axis_angle_z",
        "gripper",
    ],
    action_type=None,
)

__all__ = ["LIBERO_OSC"]
