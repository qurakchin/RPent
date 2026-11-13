# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance contributed by the RoboCasa tool surface."""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.assembly import PromptSection, sections

LOCALIZATION = """
PRIMARY TOOL — back_project_batch: Pass a list of [row, col] pixels from the
calibration-frame agentview image. Always sample 3-8 pixels firmly on the object's
top surface and use the returned summary.median_xyz as the object's world coordinate.
Avoid thin rims, edges, and table-gaps.

FINDING OBJECTS — query_world_map: Use z_min/z_max to find objects at specific
heights. Typical: z_min=0.85, z_max=0.95 finds countertop objects.
Use camera='navview' with z_min=0.0, z_max=0.12 to find walkable floor.

CAMERA IMAGE ROLES:
- calibration_frame agentview: USE THIS IMAGE for back_project_batch pixel picking.
  The pixel coordinates map directly to the world map.
- nav_view: Base-mounted forward-down camera. Floor pixels (z≈0) are walkable.
- wrist: Eye-in-hand camera. MOVES with gripper. Good for close-range refinement.
"""

NAVIGATION = """
Use navigate_to for long-range base movement. The base drives toward the target
(x,y) and stops facing it. Use tol = desired approach distance + object half-depth:
navigate_to with tol=0.6m stops about 0.6m in front of the target, facing it.

Use move_base for fine adjustments (small turns, short forward/backward nudges).
Keep each move_base modest: forward ≤ 0.4, turn ≤ 0.3, steps ≤ 20.

Use the navview camera to check if the path ahead is clear.
"""

PRIMITIVES = """
AVAILABLE PRIMITIVES (arguments are defined by each tool's schema):
- navigate_to: drive the base to a world (x, y) target.
- move_base: raw base velocity in the robot-local frame.
- move_to: servo the arm to a world xyz.
- move_delta: relative arm nudge from the current position.
- rotate_pitch: tilt the wrist forward or back while holding xyz.
- set_gripper: close or open the gripper.
- release: open the gripper to drop.
- scripted_grasp: coarse fallback grasp (open, hover, descend, close, lift).
- rldx_skill: VLA full-body skill (arm + base).
- rldx_arm: VLA arm-only skill (base clamped).
- reset: restart the episode (only in EXPLORE mode).

PERCEPTION TOOLS:
- view_env_state: read state and images.
- back_project_batch: one or more pixel lookups with a median summary.
- query_world_map: find objects by height or region.
- finish: signal task completion.
"""

VLA_RULES = """
VLA EXECUTION RULES (the single most important rule):
1. Every rldx_skill / rldx_arm call must pass the complete live task_language
   verbatim. Never shorten, paraphrase, or replace it with an atomic sub-task.
2. After each VLA call, inspect its returned state and current RGB-D. Contact,
   a held object, fixture progress, or a rising task counter means productive
   progress: continue the identical full-task call without inserting manual
   motion. Manual commands wipe VLA frame history.
3. Omit max_chunks. Ordinary RoboCasa defaults to 70; Target50 exports
   RLDX_MAX_CHUNKS=40 to lock its protocol. Do NOT pass settle_patience
   (default 999 disables settle detection).
4. A 'cap' alone is not failure. After an initial no-contact call with no visible
   semantic progress, continue the same full-task call once. Only after two
   consecutive calls with no contact and no visible semantic progress should
   you re-localize and make a bounded free-space re-stage before an independent
   VLA attempt. Never repeat an unchanged no-contact attempt indefinitely.
5. The vla_desync flag in view_env_state tells you if the VLA history was
   invalidated. If True, the next VLA call will start fresh.
"""

GRIPPER_RULES = """
GRIPPER RULES:
- For CARRYING a grasped object: OMIT the gripper parameter (it defaults to 'hold',
  which maintains the current finger width without crushing the object).
- +1 = actively close the gripper.
- -1 = actively open the gripper.
- 'hold' = maintain current finger width (safe for carrying).
- release is the safe way to drop an object.
- Carrying with -1 silently drops the object.
"""


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the RoboCasa tool guidance for this run."""
    return sections(
        __file__,
        {
            "LOCALIZATION": LOCALIZATION,
            "NAVIGATION": NAVIGATION,
            "PRIMITIVES": PRIMITIVES,
            "VLA RULES": VLA_RULES,
            "GRIPPER RULES": GRIPPER_RULES,
        },
    )
