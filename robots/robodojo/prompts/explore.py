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

"""RoboDojo exploration prompt for transferable manipulation memory."""

from __future__ import annotations

from collections.abc import Mapping

from robots.robodojo.prompts import evaluate as base
from robots.robodojo.prompts.policy import POLICY_PROMPTS
from rpent.prompt.assembly import PromptSection, sections
from rpent.utils.templates import substitute

GOAL = """Solve the current task at its fixed seed and layout, then produce
evidence-backed memory for evaluation on other seeds and layouts. This is
exploration session {{session_number}} of {{session_max}}. A successful episode
provides a strategy to adapt, not a trajectory to replay unchanged."""

READ_ORDER = """Before the first robot action:
1. Read robots/robodojo/guides/GUIDE_RPENT.md completely.
2. Inspect view_env_state and the head and wrist images. Read the native task
   instruction and note both arms' initial end-effector positions and orientations.
3. Read the published task-specific JSON/JSONL pair and task-family notes when
   present, plus relevant global lessons from {{memory_dir}}/MEMORY.md.
4. Read {{memory_inbox}}/wip/notes.md when present.

Use a successful JSON audit for its phase plan and reasoning, and its JSONL
recipe for action order, parameters and {{policy_name}} cadence. Preserve arm
roles required by the current instruction; reconsider roles chosen only for a
previous layout. If memory is absent, proceed from observation."""

RULES = """This session allows {{explore_attempts_per_session}} attempts including the
initial episode (0 means no attempt-count limit; other run limits still apply).

reset restores the same task, seed group and layout. Re-run perception and do
not reuse stale pixels or coordinates. Before each reset or unsolved finish,
save the attempt number, actual commands, observed progress, failure evidence
and next changed strategy variable under
{{output_dir}}/attempts/attempt_<N>_failed.json. Never overwrite an earlier
attempt. Append bounded observations to {{memory_inbox}}/wip/notes.md.
{{retry_strategy}}
An unsolved finish is refused while a finite attempt budget remains. After
native success, stop motion; reset is refused. Use the remaining turns to
record what worked and the uncertainties before calling finish."""

OUTPUT = """Reserve time to close out the attempt and write
{{output_dir}}/{{recipe_tag}}.json before calling finish. Include task, seed,
layout, verbatim instruction, attempts, native_success, final_state,
memory_files_read and uncertainties. If unsolved, reference the failed-attempt
archives and claim no successful trajectory.

On success, re-read the current attempt's recorded trajectory, starting after
the most recent reset if one occurred.
Its ordered strategy_notes must account for every exported action and SAM3
call with actual parameters, trace step, phase, observed result and the reason
for any {{policy_name}}/primitive switch. Do not invent, omit or reorder calls.
The runner exports {{recipe_tag}}_recipe.jsonl from recorded motion commands
and SAM3 calls that found a mask without an error, in invocation order.
Finding a mask does not establish correct identity.
The audit/recipe pair is published only when native success is confirmed."""

MEMORY = """Only after success, consolidate working notes and the successful
trajectory into {{memory_inbox}}/task-family_{{recipe_tag}}_draft.md. Write a
compact reference that helps evaluation adapt the strategy to a new scene:
- Recognition: observed visual cues, useful SAM3 descriptions and how identity
  was checked; distinguish object recognition from locating a contact feature.
- Phase plan: prerequisites, actions, visible completion gates, protected
  relations and terminal actions. Explain arm roles and whether the instruction
  requires them or the observed layout motivated them.
- Control choices: {{memory_control}}, Primitive use, chunk choices and the
  observed reason for continuing or switching. Keep exact tested parameters in
  the audit; include reusable settings with their conditions of use.
- Action costs: record observed costs for the main phases and required terminal
  motions, distinguishing productive actions from failed attempts and recovery.
  Treat these costs as evidence from this episode, not fixed budgets for new
  scenes. Use recorded action counters; do not invent missing measurements.
- Adaptation: what to re-identify, measure or decide on a new seed/layout,
  including approach geometry, grasp offsets, clearance and release conditions.
- Recovery and limits: failure evidence, changes tried, what subsequently
  worked, unresolved causes and situations where the strategy may not apply.

Keep scene coordinates in the audit, not reusable guidance. One seed/layout
supports single-shot confidence, even after several attempts; it does not
establish robustness across scenes. Use the recorded evidence after success,
not additional robot motion, to prepare memory.
Use the shared task-family frontmatter with a bare `id`, `suite: robodojo`,
`regime: {{env_cfg_type}}`, `task_id: {{task}}`, the observed native
instruction, `evidence.cells: [{{recipe_tag}}]`, and the attempt count.

When evidence supports a cross-task lesson, write a separate
{{memory_inbox}}/<bare-id>.md in the shared global shape, with its limits and
what would falsify it. A single layout warrants single-shot confidence only.
Read existing relevant leaves before proposing a lesson, and use the shared
proposal contract for corroboration or contradiction. If no new global lesson
is supported, say so rather than inventing one.

During failed attempts, write lessons only in wip/. The shared finalizer merges
valid inbox proposals and updates MEMORY.md after the run; do not claim
publication before it completes."""


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Assemble exploration rules with shared perception and control guidance."""
    prompt = {
        "ROLE AND RULES": base.ROLE_AND_RULES,
        "EXPLORATION GOAL": GOAL,
        "READ ORDER AND MEMORY TRANSFER": READ_ORDER,
        "PHASE CHECKS AND COMPLETION": base.PHASE_CHECKS,
        "SAFETY": base.SAFETY,
        "REWARD AND SCORE": base.REWARD,
        "EXPLORATION": RULES,
        "OUTPUT DISCIPLINE": OUTPUT,
        "MEMORY CONSOLIDATION": MEMORY,
    }
    backend = (variables or {}).get("vla_backend") or "vpp2"
    return sections(__file__, substitute(prompt, POLICY_PROMPTS[backend]))
