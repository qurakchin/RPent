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

"""YAM wire contract reported by the apxinf VLA server.

A model service may not import a robot slice, so it keeps its own copy of the
identity the control station expects. The platform contract test keeps it
equal to ``robots/yam/contracts.py``.
"""

from __future__ import annotations

# Identity a YAM Pi0.5 VLA server must report back to the control station.
YAM_VLA_CONTRACT = {
    "runtime": "yam_vla",
    "policy_name": "pi05_yam_joint",
    "camera_order": ["top", "left", "right"],
    "state_layout": "qpos14",
    "action_layout": "qpos14",
    "action_dim": 14,
    "action_horizon": 30,
    "use_length": 5,
}
