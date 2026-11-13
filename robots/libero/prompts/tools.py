# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance contributed by the LIBERO tool surface.

Every section here tells the model how to use an exposed tool: the runtime it
calls into, localization with ``back_project`` and ``segment``, the mandatory
perception pass, and the workflow that orders those calls. Task techniques,
per-task recipes, and geometry notes are domain knowledge and live in the
domain prompt; the shared Motion/Scene families will eventually replace this
module's text.
"""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.assembly import PromptSection, section_source, sections
from rpent.prompt.utils import Numbered

RUNTIME = """A server process (`env_server.py`) is already running. It has Pi0.5 loaded and a
single-env LIBERO sim. The runner manages the server and exposes structured
tools. Do not start, stop, restart, or otherwise manage `env_server.py`.

- Do NOT issue file-based protocol commands.
- Do NOT emit plain-text pseudo tool calls or JSON action commands.
- Call the real structured tools exposed by the runtime.
- Use bare tool names in this prompt: `move_to`, `pi0_pick`, `release`,
  `set_gripper`, `rotate_wrist`, `rotate_pitch`, `move_pose`, `pi0_doubled`,
  `view_env_state`, `view_camera_meta`, `back_project`, `segment`,
  `read_text_file`, `write_text_file`, `list_dir`, `finish`.
- Under some runtimes these same tools may appear namespaced; call the actual tool
  name shown in your tool list, preserving the same arguments and semantics.

Each state record exposes `step`, top-level `task_language`,
`terminated`, `truncated`, coord-free `state`, an `artifacts`
list of logical base names, and a `log`. Storage paths are internal; do not
construct or parse them.

Canonical observation keys include `agentview_policy.png`, `agentview.png`,
`agentview_high.png`, `agentview_depth.npz`, `agentview_world.npz`,
`agentview_world_high.npz`, `agentview_metadata.json`, `wrist.png`,
`wrist_high.png`, `wrist_depth.npz`, `wrist_world.npz`,
`wrist_world_high.npz`, and `wrist_metadata.json`.

Use `view_env_state` to retrieve a record. It embeds the policy image and the
best available agentview and wrist images, preferring the matching `*_high.png`
artifact. Use `view_camera_meta`, `back_project`, and `segment` to consume
metadata and world maps without opening artifacts directly. Step `0` is the
initial state; step `-1` selects the latest state."""

LOCALIZATION = """This is the core of perception-isolated mode. To find where an object is:

1. Look at `agentview_high.png` (1024x1024 — PREFER THIS; fall back to
  `agentview.png` only if the high-resolution artifact is absent) and find the target
   object's pixel (row, col). (row = vertical/y from top, col = horizontal/x
   from left.)
2. Call `back_project` on that pixel and step. It uses the high-resolution world
   map by default; select the low-resolution map only for a pixel taken from a
   256x256 image. The geometry (K⁻¹ back-projection
   + extrinsic) is already done for you. Just use the returned `world_xyz`; do
   NOT write back-projection math yourself unless debugging a tool failure. NEVER
   mix hi-res pixels with low-res world maps or vice versa.

   The returned value is the object's SURFACE point under that pixel. For a
   grasp/place target use its x,y; for z use the object's resting height (sample a
   pixel on the bare table next to it, or use table z ~0.9 kitchen / ~0.42
   table-top).
3. Sample a few pixels on the object and median the world xy — robust to a single
   mis-picked pixel. (Tip: avoid pixels on the object's thin rim/edge or the gap
   to the table — those index a background/edge depth and give a world point
   metres away. Pick pixels firmly on the object's top surface.)

ALWAYS apply the manipulation offsets from memory to the PERCEIVED position
(e.g. BOWL: eef_y = plate_y + 0.045). Verify visually in `agentview_high.png`
after moving."""

PERCEPTION_ALGORITHM = """This is the default perception algorithm for EVERY cell (from the 80-task
localization sweep: `agentview_identity_wrist_geometry_except_basket`).
Agentview chooses WHAT the target is; wrist refines WHERE that already-chosen
candidate is. Do NOT invert those roles.

CORE RULE:
  • Non-basket objects/surfaces: agentview hi-res is the semantic AUTHORITY.
    The wrist is ONLY a geometry/depth refinement camera for the SAME agentview
    candidate. NEVER let the wrist freely re-identify a non-basket target — in
    failed probes the wrist locked onto a look-alike hundreds of pixels away
    while agentview had the right one.
  • Basket / basket_cavity: wrist MAY also confirm/refine, because a basket is a
    geometric container and the close view finds the true interior center (not
    the rim). Basket failures are rim/edge bias, not semantic confusion.

ALGORITHM (run this BEFORE manipulating):

1. From the initial `task_language` + `agentview_high.png` +
   object_names, infer the task-relevant TARGETS and DESTINATIONS (language only;
   never BDDL/poses).

2. GLOBAL SEMANTIC PASS (agentview hi-res): in `agentview_high.png` choose each
   target/destination candidate by RGB, label/shape, and global spatial relation.
   For duplicates (two bowls/plates/mugs) pick by RELATION (on stove, on cookie
   box, left/right/front/back), not `_1/_2`. For sauce/can/box groceries use the
   front/side label + package shape + colour + layout — top-down wrist label
   reading is NOT trustworthy. Classify destination surfaces (plate vs stove
   burner vs cabinet/drawer vs basket) semantically in RGB here.

3. COARSE XYZ (agentview): pick 3-8 pixels firmly on the chosen candidate in
  `agentview_high.png`, call `back_project` on the SAME pixels, take the median.
   Avoid edges/holes/shadows/table-gaps. This median is the IDENTITY ANCHOR for
   that entity.

4. WRIST GEOMETRY REFINE (non-basket): `move_to` ~15-20cm above the agentview
   anchor xy, then refine the SAME candidate's surface/center from the wrist:
     - accept a wrist xy ONLY if it is within ~3-5cm of the agentview anchor;
     - if the wrist xy jumps >5cm, REJECT it (it hit a look-alike/background) and
       keep the agentview xyz, or nudge and re-observe;
     - the wrist may NOT override the agentview semantic choice — it only sharpens
       coordinates when geometry is consistent.

5. BASKET SPECIAL CASE: for `basket`/cavity, agentview finds it globally, then the
   wrist confirms/refines the true INTERIOR center (place objects at the open
   interior, not the rim/outer wall). Re-localize the cavity if the basket moved.

6. MANDATORY PRE-TASK PERCEPTION PASS — DO NOT START MANIPULATION UNTIL THIS
   TABLE EXISTS in your reasoning. One row per task-relevant entity (every movable
   target, every destination/support/fixture, every relation landmark), each with:
     - name_or_role (e.g. target_1, basket_cavity, plate_surface, stove_region)
     - agentview_evidence (why this is the right semantic candidate/relation)
     - agentview_pixels_rc (3-8 hi-res pixels) + agentview_xyz (median back_project)
     - wrist_refine: accepted | rejected | basket_confirmed (+ wrist_xyz if kept)
     - final_xyz (what you will plan with)
     - uncertainty (indistinguishable can, duplicate class, basket rim bias, …)
   If an entity is too ambiguous to identify, SAY SO before acting — do not let
   Pi0 or the wrist make a free semantic choice for you.

7. FINAL READY CHECK before the first pick/place: every target+destination has a
   final_xyz; non-basket wrist refinements are spatially consistent with
   agentview; basket/cavity points are interior-centered; manipulation offsets are
   planned from the perceived final_xyz. If this fails, keep perceiving — only
   then start the manipulation plan. Re-verify with the newest image after every
   command and update the table if anything moves.

(xyz from agentview and wrist `back_project` are in the SAME world frame,
directly comparable. Do NOT blindly average them — accept wrist coords only when
consistent with the agentview anchor, or for basket/cavity geometry.)"""

WAM_ROLE = (
    "You control a LIBERO robot using a WAM and scripted tools. "
    "Tool names may appear as mcp__rpent__<name> in SDK planners."
)

WAM_WORKFLOW = (
    "Inspect view_env_state at step 0. Use wam_act to execute "
    "bounded action chunks, then inspect the new state and images before "
    "continuing. Begin with the native full task by omitting prompt. "
    "Keep that instruction while progress is visible. Use a short, "
    "grounded subtask only to address an observed failure or lack of "
    "progress; the prompt applies only to that call. Start with one chunk "
    "and inspect before continuing (at most four per call). Each chunk "
    "executes the worker's returned actions; episode-end checks prevent the next chunk. wam_act "
    "does not stop when a grasp completes. Check subtasks visually; "
    "success and terminated refer to the full task, while truncated "
    "means the action budget is exhausted. "
    "For scripted motion, localize targets "
    "using back_project or segment; never invent coordinates. Gripper +1 "
    "closes and -1 opens. Preserve +1 while carrying an object."
)

WAM_OUTCOME = (
    "This is one evaluation episode. Do not reset it. Stop acting "
    "when the episode terminates or truncates. Report success only when the "
    "environment reports terminated=true. Call finish with the observed "
    "outcome; a model prediction alone is not evidence of task success."
)


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


def tool_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the tool guidance for the selected policy and memory profile."""
    variables = variables or {}
    if variables.get("policy_kind") == "wam":
        return sections(
            __file__,
            {"ROLE": WAM_ROLE, "WORKFLOW": WAM_WORKFLOW, "OUTCOME": WAM_OUTCOME},
        )
    enabled = bool(variables.get("enable_direct_action", False))
    if variables.get("mode", "eval") == "explore":
        steps = EXPLORE_WORKFLOW_STEPS
    elif variables.get("memory_profile", "hf") == "local":
        steps = LOCAL_WORKFLOW_STEPS
    else:
        steps = EVALUATE_WORKFLOW_STEPS
    own = sections(
        __file__,
        {
            "RUNTIME": RUNTIME,
            "LOCALIZATION": LOCALIZATION,
            "PERCEPTION ALGORITHM": PERCEPTION_ALGORITHM,
        },
    )
    steps_section = PromptSection(
        "WORKFLOW",
        {"WORKFLOW": Numbered(workflow_steps(steps, enabled))},
        source=section_source(__file__),
    )
    return (*own, steps_section)
