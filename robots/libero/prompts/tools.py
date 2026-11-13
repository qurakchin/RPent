# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance contributed by the LIBERO tool surface.

Perception mechanics, runtime facts, VLA usage, and the manipulation workflow
belong to the tools the model can call. Keeping them here leaves the evaluation
and exploration domain prompts about the benchmark, and gives the shared
Motion/Scene families one place to replace this text.
"""

from __future__ import annotations

from collections.abc import Mapping

from robots.libero.prompts import workflow
from rpent.prompt.assembly import PromptSection, section_source, sections
from rpent.prompt.utils import Numbered

PROVEN_LEVERS = """These techniques and per-task target zones transfer across seeds; the
coordinates do not. The solved seed-0 reference is
`{{memory_dir}}/task-specific/{{reference_tag}}.json` plus
`{{memory_dir}}/task-specific/{{reference_tag}}_recipe.jsonl`.

CRITICAL MECHANICS (cost many wasted attempts before they were nailed):
- **GRIPPER SIGN**: in `move_to` / `set_gripper`, `gripper:+1` = CLOSE/hold,
  `gripper:-1` = OPEN. To CARRY a grasped object, hold `gripper:+1` the whole way
  (carrying with `-1` silently OPENS and drops it — the #1 early bug). `set_gripper +1`
  (steps 8-12) firms the grip after a pick; for a laterally-weak CAN use steps<=5.
- **`move_pose` defaults gripper to OPEN (-1) if you omit it** — always pass
  `"gripper":1` in `move_pose` while holding an object.
- **`move_pose` threads the OSC IK singularity that `move_to` walls at** — for
  cabinet-front / microwave-cavity / deep reaches, when `move_to` stalls
  (final_dist stays high, eef retreats), switch to `move_pose` (co-vary
  xyz+pitch+yaw). It reaches several cm deeper.

GRASPING:
- **MUGS / BOWLS / CUPS grasp at the RIM, not the center**: SAM3/back-projection
  give the object CENTER; closing the gripper there grabs air. Aim
  `eef_y = object_y + 0.045` so Pi0 rim-hooks. (Mugs do NOT hang 4.5cm in -y like
  bowls — you can wrist-segment the grasped object to measure the true held offset.)
- Some objects grasp best with `pi0_pick` from the **DEFAULT HOME pose** (no
  pre-position) — Pi0 has its own approach trajectory; pre-positioning can hurt.
- **`pi0_pick` is reusable and repurposable**:
  a HIGH `lift_thresh` (e.g. 999) + `gripper_closed_thresh:0` turns it into a
  generic closed-loop CONTACT skill (used to turn the stove knob).
- **`pi0_doubled`** = Pi0 closed-loop CONTACT skill (success :=
  `terminated`). Use it for drawer/door open-close AND insertions; call it
  repeatedly.

DISAMBIGUATION / TARGETING:
- **SWAP-PERTURBED scenes (suite `*_swap`)**: the seed-0 reference's COORDINATES
  are STALE (swap re-randomizes object positions per seed), and some s0 swap
  recipes contain a literal reset — that was the old multi-attempt era UNDOING A
  WRONG-OBJECT FIRST GRAB. You cannot reset. Use the s0 ref ONLY for: WHAT the
  targets are (task_language nouns), what they LOOK like, and which Pi0 prompt
  finally worked — never for positions, never replay its command list.
  IDENTIFY-then-GRASP: before ANY pick, identify the target SEMANTICALLY in the
  global agentview, then use the wrist only for geometry. The wrist camera is a
  near-vertical close-up: it is excellent for precise depth/xy refinement, but
  weak at reading side labels or distinguishing similar grocery items
  (ketchup/BBQ/tomato sauce, soup cans, cream cheese/butter). Do NOT let the
  wrist freely re-identify a non-basket target; it often locks onto a look-alike.
  Instead: choose the target from `agentview_high.png`, compute its agentview
  xyz, move over that candidate, project/track that SAME candidate in wrist, and
  refine only its surface/center coordinates. SAM3 scores ~0.02-0.06 on brand
  nouns ("alphabet soup", "tomato sauce") — prompt by colour+shape ("the short
  red-label can") or pick pixels manually in the agentview hi-res. Pi0's own
  prompt grounding is ALSO unreliable on brand nouns (s0's first grab took a milk
  carton instead), so pre-position the eef directly OVER the agentview-identified
  + wrist-refined target before pi0_pick. A wrong first grab usually
  tips/displaces the grabbed object AND the target zone — identification errors
  are unrecoverable; spend commands on agentview ID, not on recovery.
- **"left"/"right" in libero_10 is EGOCENTRIC (robot frame): +y = robot-LEFT =
  image-RIGHT.** A geometrically-perfect placement of the WRONG target never fires
  the predicate — when a clean placement won't terminate, SUSPECT WRONG-TARGET
  before wrong-physics (this turned a "physically impossible" verdict into a solve).
- Containers can be MOVABLE (e.g. a basket slides when bumped) — descend into the
  interior CENTER from straight above, not against the rim; SAM3's centroid of a
  frame-clipped/reflective container is rim-biased, so derive the true cavity
  center from the woven-rim pixels.

PER-TASK RECIPES THAT WORKED AT SEED 0 (adapt coords to your seed):
- 2-items→basket (t0,t1,t7): place the BOX first into the EMPTY basket interior
  (descend deep, release), then drop/`pi0_pick`-lift the CAN in beside it; a
  rim-perched item can be seated with a closed-gripper downward push.
- mugs→plates (t4) / mug→plate (t6): rim-grasp, +1-hold carry, descend until the
  mug rests on the plate before release (high release → topples off).
  ⚠ t4 SINGLE-ATTEMPT LEVERS (READ — the seed-0 "win" quietly used 2 resets; you
  have NONE. 8/9 multiseed cells died to the SAME chain: Pi0 rogue-place →
  tipped mug → unrecoverable cascade. Prevent it up front):
    1. GRASP-ONLY pi0_pick: short prompt ("grasp the yellow mug" — NEVER the full
       task_language) AND `max_chunks<=8`. With 20-25 chunks Pi0 keeps driving its
       trained pick-AND-PLACE and dumps the held mug at its own trained "left"
       (+y) or at the workspace IK edge (|y|>0.27 walls z>=0.56 — unreachable
       forever). Stop Pi0 at lift; if lift isn't reached within 8 chunks,
       RE-ISSUE pi0_pick rather than raising max_chunks.
    2. The instant lift is detected: `set_gripper +1` (steps 8-12) to lock the
       grip, then YOU script the entire carry + place (Rule 1 — Pi0 never places).
    3. Measure the held-mug offset PER PICK by wrist-segmenting the HELD mug
       (offsets differ pick-to-pick: dy=-0.055 on one grasp, -0.013 on the next —
       measure each, never reuse). Place eef = plate_center − offset; descend to
       z~0.46 until the mug RESTS on the plate (OSC stalls ~0.51), then release
       and retreat STRAIGHT UP (step_clip 0.012).
    4. ORDER/PATH: after placing mug #1, plan mug #2's pick pre-position AND
       carry path so they NEVER pass over the placed mug (a graze re-tips it). A
       tipped mug is UNRECOVERABLE (no side-grasp primitive; Pi0 won't engage
       side-lying cylinders) — prevention is everything.
    5. Plates MOVE per seed (y=±0.21 at s0, ±0.30 at s8): re-localize each plate
       rim with the wrist cam and use the x_range/y_range MIDPOINTS as the true
       center (the visible-fragment median is edge-biased).
- stove (t2): turn the knob with `pi0_pick "turn on the stove", lift_thresh:999,
  gripper_closed_thresh:0`; then grasp the pan by its HANDLE, re-segment mid-carry
  to converge on the burner.
- moka→stove (t8): grasp body, carry LOW (~4cm lift) in tiny hops (step_clip
  0.006-0.01), re-clamp `set_gripper +1` between hops; "LEFT" = +y pot.
- bottle→bottom drawer + close (t3): the drawer In-region is SHALLOW
  (y≈0.075-0.227) — place at the MOUTH (y≈0.13), NOT the deep recess; `pi0_pick`
  the bottle from home pose, `rotate_pitch` it flat ALONG X (the wide footprint),
  release at the mouth, ONE short +y push seats it AND closes the drawer.
- mug→microwave + close (t9): the only UNSOLVED seed-0 cell — the round mug-in-hand
  walls ~3cm short of the In() threshold (deep narrow cavity). Try every lever
  (`pi0_doubled`, `move_pose`, push) and if it still walls, write an honest
  `terminated:false` with the max eef-y reached."""

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

KEY_HYPERPARAMETERS = """- Single-step xy within ±0.30 or OSC flips IK; split long traversals.
- lift_thresh 0.05 (flat) / 0.08 (slippery tall bottles).
- step_clip 0.025 (empty/box) / 0.015 (cans) / 0.012 (tall bottles).
- Frame: state.robot0_eef_pos[2] ≈ 0.68 LIVING_ROOM / 1.17 KITCHEN / 0.26 object.
- TALL BOTTLES: carry z=0.30, drop without descending.
- Approach high-then-vertical; recover by re-pick, not hover."""

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


def prompt_sections(
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
        steps = workflow.EXPLORE_WORKFLOW_STEPS
    elif variables.get("memory_profile", "hf") == "local":
        steps = workflow.LOCAL_WORKFLOW_STEPS
    else:
        steps = workflow.EVALUATE_WORKFLOW_STEPS
    own = sections(
        __file__,
        {
            "PROVEN LEVERS": PROVEN_LEVERS,
            "RUNTIME": RUNTIME,
            "LOCALIZATION": LOCALIZATION,
            "PERCEPTION ALGORITHM": PERCEPTION_ALGORITHM,
            "KEY HYPERPARAMETERS": KEY_HYPERPARAMETERS,
        },
    )
    steps_section = PromptSection(
        "WORKFLOW",
        {"WORKFLOW": Numbered(workflow.workflow_steps(steps, enabled))},
        source=section_source(workflow.__file__),
    )
    return (*own[:4], steps_section, own[4])
