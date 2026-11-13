# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""LIBERO workflow guidance contributed by the tool layer.

Workflow steps describe how to combine the scene, motion, memory, and file
tools. They live beside the tool guidance rather than in the domain prompt, so
evaluation and exploration share the same step text and the domain files stay
about the benchmark itself.
"""

from __future__ import annotations

EVALUATE_WORKFLOW_STEPS = (
    """READ THE GUIDES once each:
- `robots/libero/guides/strict_hybrid_guide.md`
- `robots/libero/guides/pro_hybrid_guide.md`
- `robots/libero/guides/env_calibration.md`
""",
    """INSPECT INITIAL STATE: call `view_env_state` at step 0; inspect
  `task_language`, object_names, eef pose, `agentview_high.png`,
  `wrist_high.png` if useful, and call `view_camera_meta` if needed. Identify ALL target
objects, destination surfaces, and relation landmarks named by task_language.
""",
    """READ MEMORY for the observed `task_language` and scene. The index
`{{memory_dir}}/MEMORY.md` does not name every scene a memory covers, so
`list_dir` `{{memory_dir}}/global/` and `{{memory_dir}}/task-family/` and pick
candidates by the objects, container,
fixture or motion your scene involves. Several near-identical skill files may
exist (e.g. multiple stove / basket / mug patterns); open the top candidates
and choose by the file BODY, not the index line — do NOT stop at the first name.
⭐ MANDATORY — do this even when a seed-0 recipe exists: the recipe gives the
commands, memory gives the reasoning and failure modes needed to adapt them. In
your final `strategy_notes`, RECORD the exact memory file name(s) you read (or
state "no matching task memory found").
""",
    """READ SEED-0 STRATEGY REFERENCES IF PRESENT, then solve from scratch.
Strategy references live under:
- `{{memory_dir}}/task-specific/` (solved seed-0 audit + recipe pairs:
  `<tag>.json` + `<tag>_recipe.jsonl`)
Use these for strategy_notes, prompt ladders, primitive ordering, gotchas, and
qualitative target zones. They were built on different scenes and sometimes
with older/oracle assumptions.
""",
    """RUN THE MANDATORY PRE-TASK PERCEPTION PASS (FIRST-STEP ALGORITHM above) —
localize EVERYTHING first, THEN act. Before any pick/place build the
localization table: agentview hi-res for semantic identity, `back_project` for
median xyz, wrist geometry refinement for non-basket rows (only if spatially
consistent), wrist confirmation for basket/cavity. This perception pass is the
first stage of EVERY task, even ones that look simple — a wrong-target first
grab is unrecoverable in single-attempt mode, so the cheap insurance is to
identify all entities up front. Do the FINAL READY CHECK, then plan.
""",
    """EXECUTE one primitive at a time by calling `move_to`, `pi0_pick`, or
`release`. Each tool's schema defines its arguments.

Each primitive tool blocks until the next state record is dumped and returns
the new state view, log, and embedded images. Inspect `agentview_high.png` and
`wrist_high.png` as needed, call `back_project` for geometry, decide, and repeat.
""",
    """⛔ `reset` is FORBIDDEN here
(SINGLE-ATTEMPT MODE). FORBIDDEN: `exit`, `set_object_pose`, `articulate_to`,
`js_move_to`, `carry_object`.

⚠ INFRA NOTE: `pi0_doubled` IS implemented and callable in this runtime —
verified. It runs the Pi0 VLA on a CONTACT skill (drawer/door open-close, knob
turn) with success := `terminated` (no lift / no gripper-close
assumption — unlike `pi0_pick`). If ANY prior note or reference for this cell
concluded that `pi0_doubled` is "unknown action" / missing / that
drawer-or-door articulation is an unsolvable "structural dead-end" BECAUSE no
contact primitive existed — DISREGARD that specific conclusion and actually
USE `pi0_doubled` for the drawer/door step, alternating with short capped OSC
pushes/aligns as needed. Re-prove the cell from scratch; do not inherit the
dead-end verdict.

SAM3 localization aid — `segment` (no robot motion): instead of eyeballing
a pixel, call `segment` with a plain description of the target and the camera to
use. It runs SAM3 on the current image, back-projects the mask via the matching
world map, and returns a robust median `world_xyz` plus logical
`segment_artifact` and `overlay_artifact` names. Inspect the embedded overlay
image to confirm the right object. Use the wrist camera (after parking the eef
~15–20 cm over the target) for ±1–2 cm refinement, or a point prompt for a
single pixel.
Text `prompt` and `point` are mutually exclusive; provide exactly one.
⚠ PROMPT PHRASING (SAM3 is sensitive): use a plain colour+shape+RELATION phrase,
NEVER the internal/brand name from `object_names`/BDDL. `"the akita black bowl"`
scores ~0.03 (SAM3 can't ground "akita") whereas `"the black bowl on the stove"`
scores ~0.76. Strip proper nouns (akita, glazed_rim_porcelain_…) — say what it
LOOKS LIKE + where it is. Always inspect the returned overlay image to confirm
the mask landed on the right object before moving.
This is a CONVENIENCE alternative to manual back-projection — if it returns
`{"error":..., "fallback":...}` (server down / low score / no detection), walk
the prompt (drop the brand word, add the relation) or just pick a pixel in the
high-resolution image and call `back_project` yourself. It does NOT replace the
two-camera relation protocol for disambiguating identical objects.
""",
    """RECOVERY (in-place ONLY — no reset): re-localize (objects may have moved),
re-pre-position + re-pi0_pick on the next prompt-ladder rung; split long
traversals into short xy waypoints; for a door/drawer/knob use a SHORT capped
OSC push or `pi0_doubled`, never one long push — it NaNs MuJoCo. If the task is
unrecoverable within this one episode, do NOT reset — write an honest
stuck-audit (`terminated:false`) and call `finish`. Never warp.
""",
    """WHEN top-level `terminated == true` in the latest tool result:
a. Write audit `{{output_dir}}/{{recipe_tag}}.json` with:
   suite, task_id, seed, regime:"strict_perception", strategy_notes (incl. how
   you localized), pick_result, final_state (latest state's `state`),
   terminated:true.
b. Call `finish`.
If your single attempt does not solve it, write `{{output_dir}}/{{recipe_tag}}.json` with
terminated:false + strategy_notes describing what you tried in this one
episode and where it stalled. Then call `finish`. (NO reset, NO second attempt.)""",
)


(
    STEP_READ_GUIDES,
    STEP_INSPECT_INITIAL,
    _,
    _,
    STEP_PERCEPTION_PASS,
    STEP_EXECUTE,
    STEP_PRIMITIVES,
    STEP_RECOVERY,
    STEP_FINISH,
) = EVALUATE_WORKFLOW_STEPS


def allowed_primitives(enable_direct_action: bool = False) -> str:
    """List motion tools available in this run, excluding mode-specific reset."""
    names = [
        "move_to",
        "pi0_pick",
        "pi0_doubled",
        "release",
        "set_gripper",
        "rotate_wrist",
        "rotate_pitch",
        "move_pose",
    ]
    if enable_direct_action:
        names.append("execute_action")
    return (
        "ALLOWED PRIMITIVES (physics-only; full schemas in the tool list/guides):\n"
        + ", ".join(f"`{name}`" for name in names)
        + ".\n"
    )


def workflow_steps(
    steps: tuple[str, ...], enable_direct_action: bool
) -> tuple[str, ...]:
    """Attach the active primitive list to the evaluation step."""
    return tuple(
        allowed_primitives(enable_direct_action) + step
        if step in (STEP_PRIMITIVES, EXPLORE_STEP_PRIMITIVES)
        else step
        for step in steps
    )


STEP_READ_LOCAL_MEMORY = """READ THE LOCAL MEMORY FILES for the observed `task_language`:
- task audit: `{{memory_dir}}/task-specific/{{reference_tag}}.json`
- task recipe: `{{memory_dir}}/task-specific/{{reference_tag}}_recipe.jsonl`
- task-family leaf: find the matching task/regime leaf under `{{memory_dir}}/task-family/`
- global index: `{{memory_dir}}/MEMORY.md`, then only relevant leaves under
  `{{memory_dir}}/global/`

If a file is absent, state that explicitly and continue with the available
validated memory. Record the exact files used in final `strategy_notes`."""


LOCAL_WORKFLOW_STEPS = (
    STEP_READ_GUIDES,
    STEP_INSPECT_INITIAL,
    STEP_READ_LOCAL_MEMORY,
    STEP_PERCEPTION_PASS,
    STEP_EXECUTE,
    STEP_PRIMITIVES,
    STEP_RECOVERY,
    STEP_FINISH,
)


STEP_READ_MEMORY = """READ MEMORY for the observed `task_language` and scene.

The `task-family_*` write-up for this cell, when it exists, carries the
technique, per-entity `segment` phrasings, the failure table with attempt
numbers, and the fragility flags for exactly this task. If it does not exist,
say so and continue; you will be creating it.

Use `{{memory_dir}}/MEMORY.md` to rule global entries OUT fast, then read the
few leaves that match your scene. A keyword often matches several near-identical
files, so choose from the file BODY, not the index line.

RECORD the memory files you read in your audit (or state that none matched)."""

EXPLORE_STEP_PRIMITIVES = """Also allowed: `reset` (🔁 allowed here —
close out the attempt first, see below).
FORBIDDEN: `exit`, `set_object_pose`, `articulate_to`, `js_move_to`,
`carry_object`.
"""

EXPLORE_STEP_RECOVERY = """RECOVERY (in-place FIRST, then reset): re-localize (objects may have moved);
re-pre-position and re-`pi0_pick` on the next prompt-ladder rung; split long
traversals into short xy waypoints; for a door/drawer/knob use a SHORT capped
OSC push or `pi0_doubled`, never one long push — it NaNs MuJoCo. If the episode
is unrecoverable, close out the attempt, `reset`, and try a changed plan.
Never warp.
"""

STEP_CLOSE_OUT = """CLOSE OUT EVERY FAILED ATTEMPT — the moment an attempt ends, whether you are
about to `reset` or about to stop. Two steps, in order:

a. ARCHIVE IT. Write `{{output_dir}}/attempts/attempt_<N>_failed.json` (N starts
   at 1 and CONTINUES across attempts — never overwrite an existing file) with:
   suite, task, seed, `libero_terminated:false`, your final state, the command
   sequence you issued, `changed_lever_vs_attempt<N-1>` naming the one thing you
   varied (omit on attempt 1), and `strategy_notes` saying exactly what you tried
   and WHY it failed. Write it as if a stranger had to reconstruct your reasoning —
   this is what the final task-family write-up is mined from, and what the NEXT agent
   on this cell reads before acting.

b. NOTE WHAT YOU LEARNED, NOW — as WORKING NOTES, not as corpus entries. Append
   to `{{memory_inbox}}/wip/notes.md`: what this attempt established, the
   measurements behind it, and which walls you hit. One short section per
   attempt, headed `## Attempt <N>`. Write it here rather than at the end
   because this is when the mechanism is clearest in your mind.

   ⚠ These are NOTES, not conclusions. Phrase walls as observations bounded by
   what you actually varied — "scripted -y pushes in small per-step increments
   stall at eef y≈-0.118", never "the drawer is kinematically unreachable". Name the
   method the wall was measured under; you do not yet know which walls are
   properties of the task and which are properties of your approach.

   ⚠ Nothing goes into the final `task-family`/`global` files or the `task-specific` layer at
   this point. Those are written once, after the cell is solved.

Then `reset` and try again with a plan that differs in a NAMED lever.
"""

EXPLORE_STEP_FINISH = """WHEN state.libero_terminated == True — or one of the Rule 4 (a)/(b)/(c)
conditions permits you to stop. If none holds and the episode is stuck, do NOT
come here: close out the attempt and `reset` instead.
a. If SOLVED: write the audit so it MATCHES the exported recipe — see DISTIL
   step (a) for the correspondence rules and the self-check.
   If UNSOLVED: write `{{output_dir}}/{{recipe_tag}}.json` recording suite,
   task_id, seed, regime, `libero_terminated:false`, total attempts,
   final_state, which Rule 4 condition permits you to stop, and where each
   attempt stalled. Claim NO trajectory — there is no recipe to match.
b. Run the DISTIL pass below.
c. Call `finish`."""

STEP_DISTIL = """DISTIL — consolidate this cell into memory. Budget ~25 tool calls.

⚠ Write ONLY under `{{memory_inbox}}/` (via `write_text_file`). The shared
proposal contract defines the shape, the bare `id`, and YAML quoting.

⚠ THIS PASS RUNS ONLY WHEN THE CELL IS SOLVED. If it is not, write the unsolved
audit (WORKFLOW), leave `wip/notes.md` and the attempt archives as they are, and
stop. Nothing is promoted from `wip/`.

When the cell IS solved, consolidate in one pass: re-read `wip/notes.md` and
every `attempts/*.json`, then write the three layers below. Each wall you noted
along the way is now decidable — say which ones the winning run went THROUGH
(they were artefacts of the method) and which it went AROUND (they were real).

a. TASK LAYER — **ONLY IF SOLVED.** The audit JSON and the recipe JSONL must be
   a MATCHED PAIR describing the SAME trajectory. Write the audit from the
   successful portion of `states.json`. After you call `finish`, the Python
   runner exports the recipe from that ground-truth trace; after a `reset` it
   keeps only commands issued after the LAST reset — exactly the sequence that
   worked. The automatic finalizer publishes the pair only when both files
   exist and the environment reported `libero_terminated:true`.
     - `strategy_notes` states the winning sequence step by step, in the same
       order as the successful state trace, with the parameters actually used.
       How you localized belongs in one opening sentence; the failure history
       belongs in the task-family write-up and the attempt archives, not here.
     - `pick_result` keys name the RECIPE STEPS they came from (e.g.
       `bowl_pi0_pick_step3`), not bare object names.
     - Record suite, task_id, seed, regime:"strict_perception", final_state,
       `libero_terminated:true`, and how many attempts it took.
     - SELF-CHECK: re-read the successful state trace and your notes side by
       side. Every manipulation command must be accounted for, and the notes
       must not invent a step absent from the trace.

b. TASK-FAMILY LAYER -> `{{memory_inbox}}/task-family_{{recipe_tag}}_draft.md`. ONE file for
   this task, updated at every close-out so the failure table grows across
   attempts. This is what a future run on this task at another seed reads first.
   Use the shared task-family shape with a bare `id`, `suite: <suite family>`
   such as `libero10`, `regime` set to the perturbation axis
   (task|swap|lan|object), the verbatim initial `task_language`,
   `evidence.cells: [{{recipe_tag}}]`, and the attempt/seed evidence. The merge
   step derives `task-family_<suite>_<regime>_t<task_id>`.

   Headings VERBATIM — this structure is what has worked in this corpus:

     ## Applicable pattern         <what this task is really testing, 1-2 lines>
     ## Winning technique          <the sequence + per-step success criteria, no
                                    absolute xyz. If NOT yet solved, title this
                                    `## Best known approach (UNVALIDATED)` — a
                                    recipe that never worked must never read
                                    like one that did.>
     ## Magic numbers              <default AND usable band, e.g.
                                    `chunks 30 (band 28-32)`, never a bare number. Each
                                    NEVER-do-this constraint on its own line.>
     ## Failure modes              <table, one row per failed attempt:
                                    | symptom | root cause (A<N>) | fix |
                                    Attempt numbers matter: "A3 died here" beats
                                    "be careful". Append rows, never rewrite.>
     ## Re-localization per scene  <per entity: the `segment` phrasing that
                                    worked + fallbacks, what it LOOKS like, what
                                    it is confused with, the reject rule, the
                                    score floor. State that this run's absolutes
                                    must NOT be cached; list them as
                                    counter-examples only.>
     ## Fragility flags            <the step most likely to break + its fallback>
     ## Difficulty and reliability <attempts to convergence, expected
                                    single-shot rate, and an HONEST record of
                                    whatever stayed unsolved>
     ## Cross-refs                 <[[id]] links to global memories>

c. GLOBAL LAYER -> `{{memory_inbox}}/<bare-id>.md`, ONE lesson per file. This
   is the deepest layer: the task-family write-up says what worked for
   THIS task, global says what it teaches about the ROBOT — a lesson still true
   on a task with different objects and a different fixture, backed by a
   mechanism you can state (kinematics, OSC/IK, Pi0's training distribution,
   SAM3 grounding, simulator behaviour). "It worked here" is not a mechanism;
   anything narrower belongs in (b) as a line, not as its own file.

   Write these from the SOLVED trajectory, not from the failures. The useful
   form is usually "X appeared impossible until Y" — the walls the winning run
   went through, and what actually moved them. A note in `wip/` that the winning
   run contradicted must NOT be promoted; if it is genuinely still true under
   stated conditions, promote it WITH those conditions in `applies_when`.
   Use the shared global shape with a bare `id`; `<kind>` is one of
   primitive|perception|strategy|failure and `<slug>` is 2-5 kebab-case words
   naming the LESSON — not the task, not the objects. Add `title` as one
   imperative sentence, `symptom: [...]` (words a stuck agent would search for),
   and `related`. Body:

     <one-sentence claim>

     **Why:**          <the mechanism. If you do not know it, write "observed,
                       cause unknown" — an honest unknown is useful, an invented
                       cause is harmful.>
     **How to apply:** <executable: ranges, signs, ordering, thresholds>
     **Falsify:**      <the observation that would disprove this>
     **Related:**      <[[id]] links>

d. DEDUPE — before writing a global file, use the shared proposal contract:
   corroborate an existing entry by proposing the same bare `id` with this cell
   added, and raise a contradiction as a separate proposal rather than editing
   the published entry. Compare against the file BODY, not the index line.

e. REPORT in your final message: how many lessons you considered, how they split
   across the three layers, how many existing entries you corroborated, and how
   many contradictions you raised."""


(
    BASE_STEP_READ_GUIDES,
    BASE_STEP_INSPECT_INITIAL,
    _,
    BASE_STEP_READ_SEED0_REFS,
    BASE_STEP_PERCEPTION_PASS,
    BASE_STEP_EXECUTE,
    _,
    _,
    _,
) = EVALUATE_WORKFLOW_STEPS

EXPLORE_WORKFLOW_STEPS = (
    BASE_STEP_READ_GUIDES,
    BASE_STEP_INSPECT_INITIAL,
    STEP_READ_MEMORY,
    BASE_STEP_READ_SEED0_REFS,
    BASE_STEP_PERCEPTION_PASS,
    BASE_STEP_EXECUTE,
    EXPLORE_STEP_PRIMITIVES,
    EXPLORE_STEP_RECOVERY,
    STEP_CLOSE_OUT,
    EXPLORE_STEP_FINISH,
    STEP_DISTIL,
)
