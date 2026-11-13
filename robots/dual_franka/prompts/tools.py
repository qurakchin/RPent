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

"""Tool guidance for the dual-Franka runtime."""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.assembly import PromptSection, sections
from rpent.prompt.utils import Numbered

CAMERA_AND_PROJECTION = (
    "Read describe_dual_franka_setup or view_env_state for available_camera_views "
    "before choosing a camera name. The tool schema does not enumerate views "
    "because real deployments may register additional cameras in the robot config.",
    "Use back_project only for pixels selected from the named camera image. "
    "Choose a pixel well inside visible material of the named target object or "
    "target container, away from silhouettes, rims, walls, wires, occluders, and "
    "background. Never project image-space air above an object.",
    "When SAM3 is available, use segment on a registered localization camera to "
    "segment visible target objects or destination regions before manual pixel projection. "
    "Inspect the returned mask overlay yourself; trust the returned right_base "
    "point only when the mask and median marker cover the intended target.",
    "SAM3 text prompts are phrase-sensitive. Prefer short color/object/relation "
    "phrases. If a text prompt returns a very low score, retry a "
    "shorter/rephrased prompt or point prompt rather than lowering min_score.",
    "After every projection, inspect the returned annotated camera image. "
    "The marker center must be visibly inside the intended target material; "
    "selection_valid=true is necessary but not sufficient. Retry a more central "
    "interior pixel whenever the marker looks wrong.",
    "Treat right_base as the only world coordinate frame for agent reasoning. "
    "After a verified projection, trust the returned right_base xyz and TCP-to-"
    "point deltas as the primary metric evidence; do not override them with "
    "unaided 2D RGB distance guesses.",
    "Do not move an arm or held object merely to improve camera visibility. If "
    "visibility is insufficient, mark the state uncertain or stop for operator "
    "feedback instead of performing active-vision motions.",
)

VLA_GATES = (
    "Use VLA segment tools for contact-rich motion: vla_right_grasp, "
    "vla_handoff, and vla_left_place.",
    "vla_right_grasp ends after right gripper closure plus lift; vla_handoff "
    "ends after right gripper opening plus a configured release delay; "
    "vla_left_place ends after left gripper opening plus lift. These boundaries "
    "only mean a segment ended; verify physical success from images, gripper "
    "widths/open flags, and projection geometry before continuing.",
    "After a grasp VLA, do not decide lifted/held status from 2D appearance "
    "alone. Check right gripper state and the latest inline image. If held status "
    "is unclear, project the best visible held-object surface when possible and "
    "compare right_base z primarily with the source/table height or pre-grasp "
    "source projection.",
    "If a verified projection of the intended object or held-object surface is "
    "higher than source/table height, treat the grasp as successful and proceed "
    "to vla_handoff. Mark failure only when verified projection shows the same "
    "object still at table height and gripper/image evidence shows the right "
    "gripper is empty or not supporting it.",
    "After a confirmed right-hand grasp, call vla_handoff directly. Do not use "
    "move_delta, rotate_delta, open_gripper, close_gripper, or any other "
    "rule-based primitive to prepare or reposition either arm for handoff; the VLA owns the bimanual "
    "approach, relative pose adjustment, left-hand grasp, right-hand release, "
    "and collision-aware transfer.",
    "Before vla_left_place, first verify that vla_handoff has ended and the "
    "left gripper holds the intended object. If the left hand is not clearly "
    "holding the object, do not stage for placement.",
    "For placement staging, project a clearly valid target pixel inside the "
    "required destination, then use projected x/y only. Keep the current left "
    "TCP z with delta_z=0 by default; do not move to the projected z coordinate "
    "or add large vertical clearance. Let vla_left_place handle descent, "
    "release, and post-release lift.",
)


def tool_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return camera, projection, and VLA segment guidance for these tools."""
    return sections(
        __file__,
        {
            "CAMERA AND PROJECTION RULES": Numbered(CAMERA_AND_PROJECTION),
            "VLA SEGMENT GATES": Numbered(VLA_GATES),
        },
    )


__all__ = ["tool_sections"]
