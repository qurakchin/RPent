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

"""Robots and action-model capabilities share one copy of each wire contract."""

from robots.libero import control as libero_control
from robots.robotwin import control as robotwin_control
from robots.robotwin import observation as robotwin_observation
from rpent.robots.components import am_platforms


def test_robot_modules_reexport_shared_contracts():
    assert libero_control.LIBERO_OSC is am_platforms.LIBERO_OSC
    assert robotwin_control.ROBOTWIN_QPOS is am_platforms.ROBOTWIN_QPOS
    assert robotwin_control.ROBOTWIN_EEF is am_platforms.ROBOTWIN_EEF
    assert robotwin_control.ROBOTWIN_CONTROLLERS is am_platforms.ROBOTWIN_CONTROLLERS
    assert robotwin_observation.ROBOTWIN_CAMERAS is am_platforms.ROBOTWIN_CAMERAS


def test_controllers_are_indexed_by_action_space():
    assert set(am_platforms.ROBOTWIN_CONTROLLERS) == {
        am_platforms.ROBOTWIN_QPOS["action_space"],
        am_platforms.ROBOTWIN_EEF["action_space"],
    }
    assert (
        am_platforms.ROBOTWIN_CONTROLLERS[am_platforms.ROBOTWIN_EEF["action_space"]]
        is am_platforms.ROBOTWIN_EEF
    )


def test_yam_robot_contract_is_a_copy_of_the_shared_contract():
    from robots.yam.contracts import vla_runtime_contract

    assert vla_runtime_contract() == am_platforms.YAM_VLA_CONTRACT
    assert vla_runtime_contract() is not am_platforms.YAM_VLA_CONTRACT
    assert am_platforms.YAM_VLA_CONTRACT["camera_order"] == ["top", "left", "right"]
    assert am_platforms.YAM_VLA_CONTRACT["state_layout"] == "qpos14"
    assert am_platforms.YAM_VLA_CONTRACT["action_layout"] == "qpos14"
    assert am_platforms.YAM_VLA_CONTRACT["action_dim"] == 14
