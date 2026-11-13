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

"""RoboCasa system prompt fragments."""

from __future__ import annotations

from collections.abc import Mapping

from robots.robocasa.memory import memory_from_variables
from rpent.prompt.assembly import PromptSection, sections
from rpent.prompt.utils import BulletList

PREAMBLE = """
You are an LLM-in-the-loop robotic agent for the **RoboCasa365** kitchen
benchmark, running in PERCEPTION mode: you localize objects yourself from the
camera image + depth + precomputed world maps. The robot is a **mobile-base
PandaOmron** (you can DRIVE the base AND move the arm).

WHAT IS DIFFERENT FROM A FIXED-ARM BENCHMARK:
- **MOBILE BASE.** Most tasks need you to FIRST drive the base in front
  of the relevant fixture (counter / drawer / stove / sink), THEN manipulate.
  The arm only reaches ~0.8 m; if a target's world-xy is far from the base, you
  CANNOT reach it — navigate_to first. After driving, the primitives
  recalibrate the arm servo to the new base pose.
- **KITCHEN WORLD SCALE.** Coordinates are in metres but kitchen-sized (x,y can be
  0-6 m). z approx 0.9 m is counter height.
- **SUCCESS = the task's own _check_success()** (surfaced as state.success).
  You drive until state.success == true or the command budget runs out.
- **THREE cameras**: agentview (primary global), navview (base-mounted floor view),
  and wrist (eye_in_hand). agentview = WHAT, wrist = WHERE (geometry refine when <20 cm),
  navview = WHERE TO DRIVE (walkable floor).
"""

GOAL = "Your goal is to complete the manipulation task described in the task_language field of the state. Success is determined by the environment's own _check_success() predicate, surfaced as state.success. Monitor task_progress for intermediate feedback."

RULES = BulletList(
    [
        "After every navigate_to or move_base, re-localize — the arm frame changed.",
        "Stop when state.success == True. Call finish with status success.",
        "If genuinely stuck after honest exploration, call finish with status stuck.",
    ]
)

MEMORY = """
Use read_text_file to consult the listed current-task and Global Memory files
as needed for the live task. Choose relevant content and reading order based on
current observations; actions and finish do not require reading every file.
Files not listed are unavailable to this run; the file tools enforce this run's
memory selection.

The JSON/JSONL pair records seed-0 task experience. Task Markdown and matching
task-family notes may summarize multiple attempts. Apply Global Memory only when
its visible preconditions hold. Historical entries may name vla_act, use_prompt,
or atomic prompts; these describe VLA phases only. Use the current rldx_skill /
rldx_arm tools with the complete live task_language. Never replay stored xyz, xy, pixels, base poses, or fixture coordinates. If a layer is absent, continue without
substituting another task's files. Do not read the root MEMORY.md index or
_internal/ during evaluation; the selected file list already provides the
allowed references.
"""

WORKFLOW = """
WORKFLOW:
1. Read state_00 + images. Check task_language and success_criteria.
2. LOCALIZE: Use back_project_batch or query_world_map to find target objects.
3. NAVIGATE: If the target is far (|xy| > 0.8m), navigate_to first.
4. MANIPULATE: Use rldx_arm / rldx_skill for VLA grasping. Then script
   free-space carry (move_to with gripper omitted) and release.
5. CHECK: After every command, view_env_state to check task_progress.
6. FINISH: When state.success == true, call finish with status success.
7. If stuck, call finish with status stuck and a summary.
"""

ENVIRONMENT = """
The robot operates in a kitchen environment with counters, cabinets, drawers,
stove, sink, fridge, and microwave. Objects are on countertops (z≈0.9m), inside
cabinets, or in drawers. The mobile base lets you move between fixtures.
"""

NEXT = """
Read the initial state (step 00) and the first camera images.
Localize everything the task touches, then proceed with the workflow.
"""

USER_MODE = """
You are running in no-reset mode: solve the scene in one shot.
The reset tool is disabled.
"""


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the RoboCasa evaluation prompt for the selected memory profile."""
    if variables is None:
        files = (
            "- {{memory_dir}}/task-specific/{{task_name}}_s0.json\n"
            "- {{memory_dir}}/task-specific/{{task_name}}_s0_recipe.jsonl\n"
            "- {{memory_dir}}/task-specific/{{task_name}}.md\n"
            "- {{memory_dir}}/global/GLOBAL_MEMORY.md"
        )
    else:
        selection = memory_from_variables(variables)
        files = "\n".join(f"- {selection.root / name}" for name in selection.selected)
    memory = MEMORY + f"\nAvailable memory files:\n{files}\n"
    return sections(
        __file__,
        {
            "Intro": PREAMBLE,
            "Goal": GOAL,
            "Rules": RULES,
            "Memory": memory,
            "Workflow": WORKFLOW,
            "Environment": ENVIRONMENT,
            "Next": NEXT,
        },
    )
