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

"""RoboDojo evaluation prompt and shared perception and control guidance."""

from __future__ import annotations

from collections.abc import Mapping

from robots.robodojo.prompts.policy import POLICY_PROMPTS
from rpent.prompt.assembly import PromptSection, sections
from rpent.utils.templates import substitute

ROLE_AND_RULES = """You control RoboDojo's dual ARX-X5 arms through registered tools.
Read the native task instruction in view_env_state before acting. Use images,
depth and robot proprioception, not hidden object poses or evaluator internals.
Do not control services or the robot through scripts, shell or direct RPC."""

READ_ORDER = """Before the first robot action, read
robots/robodojo/guides/GUIDE_RPENT.md completely. Inspect view_env_state and the
head and wrist images, read the native instruction, and note both arms' initial
end-effector positions and orientations. Bind objects, destinations and arm
roles from current observations."""

PHASE_CHECKS = """Before the first motion, read episode_status.step_limit and
remaining_steps from view_env_state. Consult relevant memory when permitted by
the run mode. State a brief phase plan covering the required subgoals, arm
roles, observable completion conditions and any required final robot posture.

The task must reach native success within the available action budget;
if remaining_steps reaches zero without native success, the episode fails.
Plan within the latest remaining_steps. Before each motion, consider its
expected action cost and the steps still needed for unfinished phases,
including required release, withdrawal and final robot posture. Use a rough
estimate grounded in tool settings and observed execution; do not assume
that a phase will finish within a fixed number of steps.

After each motion, compare the actual steps consumed with visible progress
and update the plan. Judge whether the budget is tight from the remaining
work, not a fixed percentage. As the margin narrows, focus on the first unmet
completion condition, preserve achieved subgoals and avoid speculative
detours or unchanged repetitions.

Reduce action cost only when the motion remains physically appropriate.
Do not shorten a large movement to a single waypoint merely to fit the
budget, or omit necessary support, release or settling. Resolve uncertainty
about the target, clearance and held-object state through available images
and read-only queries before spending motion steps. Keep these checks focused
and within the run timeout.

Track the phase, each hand's contents, protected relations, the first unmet
condition and the next observable gate. Apply only checks relevant to the
current instruction and phase:
- Grasp/transport: the intended object moves with the hand and remains held;
  gripper closure alone is insufficient.
- Placement/hanging: inspect alignment and support before release, then verify
  separation and that the intended relation persists during withdrawal.
- Containment/insertion: distinguish entry into the opening from resting on a
  rim or merely reaching its vicinity; inspect orientation and seating.
- Handover: verify receiver hold before giver release, then verify retained hold.
- Pushing/articulation/tool use: check the object or mechanism's actual change
  while preserving the required contact and method. Do not substitute lifting
  for pushing or release when continued holding is required.
- Material transfer/deformation: inspect the contents or shape that must change;
  source-container tilt or hand motion alone does not establish the result.
  Preserve support and complete the required terminal posture.
- Multi-object work: check counts, order and orientation required by the task;
  preserve completed objects, supports and the other hand's work.

Occlusion leaves a condition unconfirmed, not automatically failed or satisfied.
Use another available view before making an unsupported correction. Continue
useful progress within the phase; advance dependent phases only when their
prerequisites are supported.

RoboDojo placement and arrangement tasks commonly require both
arms to return to their initial end-effector positions and orientations. When
the object goals appear satisfied, check remaining relations and required
terminal actions before disturbing correct objects. If native success is
reported, stop motion immediately, including any planned return."""

SAFETY = """Native planning includes a simplified table and self-collision
checks, not a complete obstacle model of objects or the opposite arm.
Choose visible clearances and conservative waypoints. Path subsampling can
skip a planned detour. Do not claim collision-free motion or exact arrival."""

REWARD = """Do not request hidden reward details or evaluator internals."""

OUTPUT_DISCIPLINE = """Record the observed outcome and uncertainties in
{{output_dir}}/{{recipe_tag}}.json, including the native instruction, task, seed,
layout, native_success, memory_files_read, missing references and material
deviations from the reference strategy. Then call finish with the observed
status and summary.
Do not run an exploration sweep within an evaluation episode."""


MEMORY = """After inspecting the current instruction and scene, read these
published references before choosing an approach, when present:
1. {{memory_dir}}/task-specific/{{reference_tag}}.json
2. {{memory_dir}}/task-specific/{{reference_tag}}_recipe.jsonl
3. {{memory_dir}}/task-family/task-family_robodojo_{{env_cfg_type}}_t{{task}}.md
4. {{memory_dir}}/MEMORY.md for the global leaves relevant to this scene's
   manipulation or failure mode; one to three usually suffice.

Read each task reference completely. Check the returned size and content for
truncation; if truncated, read again with a limit at least equal to the
reported size. Do not treat a partial read as the complete reference.

The reference is the same exact task variant explored at seed 0, layout 0.
Keep standard and Random task-specific pairs and task-family notes separate:
do not substitute one variant's recipe for the other's. If a reference is
missing, record that absence and proceed from the available relevant global
guidance and current observations. Do not read _internal/ or failed-run drafts.

Use the JSON and task-family notes to understand phase order, observable gates,
controller choices, recovery reasons and applicability limits. Use the JSONL
as evidence of actual calls, SAM3 descriptions and {{policy_name}} chunk choices. A
successful episode can include failed approaches and corrective detours:
identify which actions made progress rather than replaying every call.

Choose arms for current reach unless the native instruction requires a
particular arm. Revalidate SAM3 identity and contact geometry; historical
pixels, coordinates and grasp offsets are not targets. Single-seed evidence,
including a probable lesson, does not establish cross-seed reliability.
Protect achieved relations and correct only the remaining blocker when a
reference strategy no longer fits the scene."""


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Assemble the evaluation prompt for the selected feedback mode."""
    prompt = {
        "ROLE AND RULES": ROLE_AND_RULES,
        "READ ORDER": READ_ORDER,
        "MEMORY": MEMORY,
        "PHASE CHECKS AND COMPLETION": PHASE_CHECKS,
        "SAFETY": SAFETY,
        "REWARD AND SCORE": REWARD,
        "OUTPUT DISCIPLINE": OUTPUT_DISCIPLINE,
    }
    if (variables or {}).get("mode") == "eval-fair":
        prompt.pop("MEMORY")
        prompt["READ ORDER"] = (
            "Inspect view_env_state and the head and wrist images before acting. "
            "Read the native instruction, note both arms' initial end-effector "
            "positions and orientations, and bind objects, destinations and arm "
            "roles from current observations."
        )
        prompt["REWARD AND SCORE"] = (
            "Task success feedback is unavailable to this client."
        )
        prompt["OUTPUT DISCIPLINE"] = (
            "Evaluation permits one episode without reset. Call finish with your "
            "observed outcome; do not claim a verified task verdict."
        )
    backend = (variables or {}).get("vla_backend") or "vpp2"
    return sections(__file__, substitute(prompt, POLICY_PROMPTS[backend]))
