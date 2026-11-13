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

"""Tool guidance for the single-Franka runtime."""

from __future__ import annotations

from collections.abc import Mapping

from rpent.prompt.utils import Numbered, PromptNode

PRIMITIVES = (
    "Express move_delta and rotate_delta in the fixed robot base frame.",
    "Never use a VLA trained for another embodiment or action normalization.",
    "For grasp tasks, open the gripper before calling vla_grasp near contact.",
)


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> Mapping[str, PromptNode]:
    """Return the motion and VLA guidance for the tools this robot exposes."""
    return {"PRIMITIVE CONVENTIONS": Numbered(PRIMITIVES)}


__all__ = ["prompt_sections"]
