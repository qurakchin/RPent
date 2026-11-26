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

"""Bounded integration of the RoboLab simulator and Pi0.5 policy."""

import os
from pathlib import Path

from tests.e2e_tests.common import (
    ToolExample,
    require_model_path,
    run_policy_chain,
)


def test_pi05_policy_chain() -> None:
    require_model_path("PI05_CHECKPOINT_PATH")
    output = Path(os.environ["RPENT_E2E_OUTPUT_DIR"]) / "policy-chain"
    result = run_policy_chain(
        robot="robolab",
        robot_argv=[
            "--task",
            "BananaInBowlTask",
            "--seed",
            "0",
            "--sim-python",
            os.environ["ROBOLAB_SIM_PYTHON"],
        ],
        output_dir=output,
        action=ToolExample("pi05_act", {"steps": 1}),
        action_count_field="executed_steps",
        before_action_calls=(ToolExample("view_env_state", {}),),
        require_post_action_image=True,
    )
    assert result["simulator_action_count"] == 1
    assert list((output / "main.png").glob("*.png"))
    assert list((output / "wrist.png").glob("*.png"))
