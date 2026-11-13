# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance contributed by the RoboDojo tool surface.

The slice-side seam for tool-family contributions. Policy-specific wording is
resolved from the backend here, so the domain prompt no longer branches on the
VLA backend for tool usage.
"""

from __future__ import annotations

from collections.abc import Mapping

from robots.robodojo.prompts.policy import POLICY_PROMPTS
from rpent.prompt.assembly import PromptSection, sections
from rpent.utils.templates import substitute

TOOL_ACCESS = """Use view_env_state to inspect recorded head and wrist images.
render captures a new synchronized observation without commanding robot motion.
Each non-readonly tool also captures a new observation after execution.
Observations and motion feedback include episode_status: step is the native
action count, step_limit is the task's total action budget, and remaining_steps
is the budget left at capture time. The top-level step is an observation index,
not an action count. Historical observations retain their historical budget."""

PERCEPTION = """Use sample_world_xyz for [row,col] pixels or query_world_map for
a half-open [r0,c0,r1,c1] region. Views are head, left_wrist and right_wrist;
use the same view and step as the source image. Coordinates are world-frame
metres. Invalid depth is not a point. segment runs SAM3 on that saved image.
Cameras are cam_head, cam_left_wrist and cam_right_wrist. Its point_rc lies in
the mask; centroid_rc may lie outside a concave mask. Use point_rc with
back_project at the returned step_idx and camera. A visible surface point is
not necessarily an object centre or a safe grasp point. Re-perceive after
motion/reset.

For SAM3, describe visible colour, shape and relative location, e.g.
"the pink bottle on the left of the table", not internal asset or brand names.
Inspect the returned red-mask overlay before using the point. A high score
alone does not prove object identity. Disambiguate look-alikes with head and
wrist views. If no mask is found, revise the description or select a visible
pixel manually; never invent coordinates from a failed detection.
Segmentation returns image pixels, not world coordinates; follow with
back_project when you need a visible surface's world position."""

TOOLS = """move_to plans a full pose. Quaternion order is wxyz; omitted
orientation and opening are held. rotate_wrist applies relative yaw about world
Z, in degrees, with the same substeps selection rules. Each executed waypoint
consumes one native action step (0.04 seconds of simulation). Fewer waypoints
give less execution time; completed means the selected commands ran, not that
the target pose was reached. set_gripper opens or closes the fingers; its
schema defines which value means which. release drops the object.
Intermediate openings are control targets, not guaranteed physical widths.
Inspect completed, executed_steps and stop_reason. final_dist_m is measured
position error, not a task-success verdict. On failure, inspect and decide
the next action; do not assume a failed call left the robot unmoved.

{{policy_tools}}"""

CONTROL = """Choose a controller for the next observable phase goal:
{{policy_role}}
- move_to: measured approach staging, verified free-space transport, withdrawal,
  return, or a specific geometric correction with understood contact geometry.
- rotate_wrist: an intentional world-Z orientation adjustment with clearance
  for the fingers and held object; it is not a general tilting command.
- set_gripper: deliberate opening adjustment or closure after alignment. Keep
  the current hold unless the phase requires changing it.
- release: transfer support to the intended surface, fixture or receiving hand
  once observations support that transfer; verify the result afterward.

Primitive staging can precede {{policy_name}}; a failed {{policy_name}} call is not a prerequisite.
Before switching, check target identity, each hand's contents, contact and
protected relations. After a primitive, inspect the actual state before
continuing. {{policy_contact}}
Do not interrupt correct contact and useful progress with speculative
primitives. An unfinished phase alone does not require switching controllers.
After an unproductive chunk, inspect whether to continue, {{policy_retry}}, improve visibility or correct the physical state.

For move_to and rotate_wrist, pick the step granularity by how fine the next
correction is: the coarse default for ordinary transport and larger changes,
progressively finer levels for short free-space moves and small orientation
adjustments, and the finest for tiny corrections. Never jump to a distant pose
at the finest level. Preserve necessary detours when choosing targets and
sampling; fewer steps do not make a large target change gentle.
After execution, inspect the achieved position, orientation and held object
before deciding whether to continue or change the approach. Minimize the total
steps needed for the phase, not just the steps in an individual call.

Choose chunks by how soon the next decision needs fresh evidence:
- 1: a new approach, uncertain progress, instability, near contact or completion,
  after a corrective primitive, or before a release/handover decision.
- 2: ordinary stable progress within a phase whose target and arm roles are clear.
- 3: a successful recipe supports a continuous phase already progressing
  correctly, with no intervening decision requiring your inspection.
Shorten the next call when those conditions change. These are selection bands,
not guarantees that a phase finishes within a fixed number of chunks.
Also account for the remaining action budget: 1, 2 and 3 chunks normally
execute {{policy_action_counts}} actions, respectively. Choose a call length that leaves
room for subsequent required actions. Near completion or with little budget
margin, prefer one chunk and inspect the result before continuing. Use the
returned action count and remaining_steps to assess actual consumption."""


def tool_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return tool guidance with the selected VLA backend's wording."""
    backend = (variables or {}).get("vla_backend") or "vpp2"
    return sections(
        __file__,
        substitute(
            {
                "TOOL ACCESS": TOOL_ACCESS,
                "PERCEPTION": PERCEPTION,
                "AVAILABLE OPERATIONS": TOOLS,
                "VLA AND PRIMITIVE CONTROL": CONTROL,
            },
            POLICY_PROMPTS[backend],
        ),
    )
