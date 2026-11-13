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

"""Tests for the curated RoboTwin prompt."""

from __future__ import annotations

from rpent.prompt.assembly import build_robot_prompt, run_axes
from rpent.robots import get_robot_spec


def test_prompts_render_with_memory_relative_paths():
    variables = {
        "task_name": "beat_block_hammer",
        "task_config": "demo_randomized",
        "seed": 100000,
        "memory_dir": "memory/robotwin",
        "reference_tag": "robotwin_beat_block_hammer_demo_randomized_s0",
        "mode": "eval",
        "planner": "api",
    }

    assembled = build_robot_prompt(
        get_robot_spec("robotwin").prompts,
        robot_name="robotwin",
        variables=variables,
        axes=run_axes(explore=False, dashboard=False, real_robot=False),
    )
    system, user = assembled.system, assembled.user

    assert "robots/robotwin/guides/GUIDE_RPENT.md" in system
    assert (
        "memory/robotwin/task-specific/robotwin_beat_block_hammer_demo_randomized_s0.json"
        in system
    )
    assert (
        "memory/robotwin/task-specific/robotwin_beat_block_hammer_demo_randomized_s0_recipe.jsonl"
        in system
    )
    assert "memory/robotwin/MEMORY.md" in system
    assert "task: beat_block_hammer" in user
    assert "seed: 100000" in user
    assert "task_config: demo_randomized" in user
    assert "{{" not in system + user
