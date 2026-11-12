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

from rpent.prompt.utils import PromptNode

CONTROL = """Every lingbot_act uses the exact complete current task_language and
use_length=50. Use one chunk near contact, near success, instability, or for a
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
do not let it silently switch to a look-alike. Pair RGB and world maps from the
same step, view, and resolution. World maps are [row,col] -> [x,y,z] metres and
may contain NaN; visible surface points are not automatically object centers.
Relocalize after occlusion, contact, or substantial arm/object motion."""


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> Mapping[str, PromptNode]:
    """Return tool guidance for the selected policy."""
    if (variables or {}).get("policy_kind") == "wam":
        return {}
    return {
        "VLA AND PRIMITIVE CONTROL": CONTROL,
        "PERCEPTION": PERCEPTION,
    }
