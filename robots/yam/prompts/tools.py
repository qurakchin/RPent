# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance for the YAM real-robot runtime."""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.assembly import PromptSection, sections

PERCEPTION = """Use top for global identity, distractors, destination, and task
progress. Use the same-side wrist view for grasp geometry and near-contact
confirmation. Pair RGB, depth, and world_xyz from the same step and view.
world_xyz is [row,col] -> [x,y,z] in metres in the YAM left-base frame; visible
surface points are not automatically object centers."""

CONTROL = """Use move_to, rotate_wrist, set_gripper, and release only after
binding the current target from fresh perception. move_to executes all
server-planned safety waypoints. Do not queue several low approaches without
observing between them. Every motion selects exactly one arm, left or right; the other
arm's commanded joints and gripper are held unchanged during that action.
Open with set_gripper's open value or release; close with set_gripper's closed
value. These are RoboTwin's dual-arm tool names.
When move_to reports failure but marks the residual recoverable, re-observe first: a small
stationary residual permits replanning, not a claim of arrival or clear contact.
When the task allows a target region, pass the lower and upper xyz bounds of a
region containing the target. Bounds must come from current perception and
account for the held object's size and destination margins. At most three plans are tested;
only one path is executed. After a recoverable residual, render again and select
a different point within that region; at most three executed candidates per
region, then change approach or use VLA. Do not enlarge a grasp/contact region
just to pass a guard. Compare requested and measured before/after displacement.
Settled means within tolerance, not that the intended displacement occurred.
Do not repeatedly command 5 mm translations against centimetre-scale tracking
error. In visually clear free space prefer meaningful centimetre-scale segments
(e.g. 3-5 cm when the complete arm and payload path permits), replanning from
measured pose after every segment. Tracking bias depends on direction, posture
and load; measure it rather than assuming a fixed gain or overshooting. If
available clearance is smaller than observed uncertainty, change route,
orientation or supported VLA strategy;
do not simply enlarge the target toward an obstacle.
Never deepen a target blindly to overcome resistance. Other servo failures require
stop. A rejected IK candidate that executed no steps and was not stopped by the
guard permits re-observation and a different reachable target; it does not require
discarding partial progress or resetting the episode. Never bypass a guard to
execute a rejected path. Runtime feedback faults and latched stops require stop.
Alternate observed single-arm actions for two-arm tasks; simultaneous coordinated
Cartesian motion is not exposed."""

VLA = """A trained YAM qpos14 VLA is connected and pi05_act is available.
Treat VLA as a primitive alongside geometric tools. Use its learned approach and
pick behavior where suitable, then use observed geometric moves for task-specific
placement when destination choice is unreliable. Choose the number of chunks
from the task, current clearance and any explicit operator preference. Each chunk
predicts from a fresh observation, but there is no Agent semantic review between
chunks. Assess both arms and the possible release region before dispatch.
Reobserve and measure progress after each call. Each prediction has 30 steps,
but only the first five execute. Do not preassign a fixed number of chunks to every grasp
or let the policy continue into an unverified release. Record the observed switching point
and chunk count as evidence, not a universal rule. Omit prompt to use the full
trained task instruction; arbitrary subgoal prompts have not been validated.
pi05_act can command both arms together."""

PRIMITIVES_ONLY = """This session has no VLA. Solve and explore using the geometric
primitives and current observations; pi05_act is not available. If the task needs
unavailable coordinated motion or contact feedback, explain that limitation
instead of requesting an untrained policy."""


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return perception, control, and policy guidance for the exposed tools."""
    policy = VLA if (variables or {}).get("vla_enabled", False) else PRIMITIVES_ONLY
    return sections(
        __file__,
        {
            "PERCEPTION": PERCEPTION,
            "CONTROL": CONTROL,
            "POLICY AVAILABILITY": policy,
        },
    )


__all__ = ["prompt_sections"]
