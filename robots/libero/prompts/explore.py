# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""LIBERO exploration domain prompt.

Exploration shares localization, runtime, and workflow guidance with
evaluation. This module keeps only what changes when the job is to find an
approach and leave knowledge behind: the mode role, the solved-only memory
contract, and the multi-attempt rule.
"""

from __future__ import annotations

from collections.abc import Mapping

from robots.libero.prompts import evaluate as base
from rpent.prompt.assembly import PromptSection, sections

ROLE = """You are an LLM-in-the-loop hybrid driver for the LIBERO PRO benchmark, running
in PERCEPTION-ISOLATED mode: you are NOT given object world coordinates. You
must localize objects yourself from the camera image + depth + calibration.

You are agent {{session_number}} of up to {{session_max}} on this cell. Every
task in this benchmark is physically solvable; a wall you hit is a property of
the approach you tried. If you exhaust your own ideas, close out your attempts,
write your notes, and hand off. A fresh agent continues from your archives
without inheriting your dead ends."""

GOAL = """YOUR GOAL: produce `state.libero_terminated == true`, then distil what you
learned into memory.

The published corpus has three layers and is read-only for this run. You write
only proposals to the inbox, never to a published layer:
  `task-specific` the audit `{{output_dir}}/{{recipe_tag}}.json` plus the replayable
           `{{recipe_tag}}_recipe.jsonl` the runner exports — a matched pair
           describing the ONE sequence that worked. SOLVED CELLS ONLY.
  `task-family`  one curated md write-up FOR THIS TASK: technique, parameter ranges,
           per-entity recognition, failure table. Grown at every attempt.
  `global` cross-task lessons, one per md file.

Write working notes at every attempt close-out; write task-family and global
proposals only after the cell is solved. If the cell is never solved, the
working notes stay in `wip/` and nothing is proposed."""

RULE_4 = """Rule 4 — 🔁 MULTI-ATTEMPT. In-place recovery includes re-localizing,
   re-pre-positioning, re-`pi0_pick`ing a missed grasp, climbing the Pi0 prompt
   ladder, re-firming the grip, and `rotate_pitch` / `move_pose`. Reset restores
   every object, including anything you tipped or shoved away, and keeps the
   exported recipe clean because it is the trace after the last reset.

   WHEN TO HAND OFF. You stop this SESSION, never the cell, and not before the
   attempt budget is spent. Running out of ideas is not a stopping condition;
   it means the next attempt should come from a class you have not tried:
     - scripted OSC pushes / servos;
     - the trained contact skill (`pi0_doubled`), from a clean pose;
     - changing how the servo advances (step size, step budget, tolerance);
     - changing the contact geometry — where on the object you touch, at what
       wrist pose;
     - changing an earlier step so the blocking state never arises.
   In the audit, say which classes you exhausted and which you would try next.

   NO teleport primitives (`set_object_pose` / `articulate_to` / `js_move_to` /
   `carry_object`)."""


def _rules() -> str:
    """Evaluation's rules with the single-attempt Rule 4 replaced."""
    rules = base.RULES
    start = rules.index("Rule 4 — ")
    return rules[:start] + RULE_4.strip() + "\n"


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the LIBERO exploration domain contribution."""
    return sections(
        __file__,
        {
            "ROLE AND MODE": ROLE,
            "YOUR GOAL": GOAL,
            "RULES (NON-NEGOTIABLE)": _rules(),
            "TASK TECHNIQUES AND TARGETS": base.TASK_TECHNIQUES,
            "MOTION NOTES": base.MOTION_NOTES,
        },
    )


__all__ = ["system_prompt"]
