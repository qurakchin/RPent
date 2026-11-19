# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Tool guidance contributed by the RoboTwin tool surface.

This is the slice-side seam for tool-family prompt contributions. When the
shared Motion and Scene tool families land, they replace this module's text;
the assembly order and the bundle contract stay the same.
"""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.assembly import PromptSection, sections

CONTROL = """Every lingbot_act uses the exact complete current task_language; the
runtime fixes the chunk length. Use one chunk near contact, near success, instability, or for a
small correction; two for ordinary stable progress; three only for a
recipe-supported continuity-sensitive phase already moving correctly. When VLA
has correct contact and visible progress, avoid interrupting it with speculative
primitives. Repeated VLA calls are allowed; after an unproductive chunk, use
fresh evidence to choose whether to continue, shorten the next chunk, or improve
binding, visibility, or physical staging first.

Prefer VLA for grasp/re-grasp, receiving-arm grasp, bimanual coordination,
insertion, hanging, tool use, and contact-rich motion. Use primitives after
verified state for measured free-space transport, staging, retreat, release, or
one small geometric correction. Never transport because a gripper merely looks
closed: also require visible target motion, elevation, or an emptied source.
Never call a primitive just to test whether it helps. For planner residuals,
guarded low approaches, physical state shaping, and wrist-sweep safety, follow
robots/robotwin/guides/GUIDE_RPENT.md and re-observe after every primitive."""

PERCEPTION = """Use the head view as semantic authority for identity,
distractors, destinations, language relations, and global progress. Use the
matching current wrist view to refine geometry for that same chosen candidate;
do not let it silently switch to a look-alike. RoboTwin has no grounding
service, so call geometry with a [row,col] pixel measured on the named view and
the quantities you need; a described target is rejected. It returns a world-frame
center, extent, pixel_rc, fit_accepted, and
warnings; inspect status and warnings instead of reading a rejected fit as
usable. Use query_world_map for deterministic samples from a known world map.
Pair RGB, depth, and world maps from the same step and view. Relocalize after
occlusion, contact, or substantial arm/object motion."""

# RoboTwin is the only host that registers MotionTools, so only its prompt
# promises the motion stop fields.
MOTION_RESULT_FIELDS = """Motion results also report `stop_reason`,
`stop_evidence`, and `pose_error`. For motion tools `stop_reason` is `arrived`,
`stalled`, `diverging`, `unsafe_motion`, `planning_rejected`, `max_steps`, or
`episode_over`; `max_steps` means the native step budget is exhausted. Other
tools may report their own `stop_reason` values; judge those by `completed` and
`execution_status`. Judge motion by these fields and a fresh observation, not
by `call_ok`."""


def tool_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return tool guidance for the selected policy."""
    if (variables or {}).get("policy_kind") == "wam":
        return ()
    return sections(
        __file__,
        {
            "VLA AND PRIMITIVE CONTROL": CONTROL,
            "PERCEPTION": PERCEPTION,
            "MOTION RESULT FIELDS": MOTION_RESULT_FIELDS,
        },
    )
