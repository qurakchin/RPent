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

from robots.dual_franka.prompts import system as system_parts
from rpent.prompt.utils import Numbered, PromptNode


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> Mapping[str, PromptNode]:
    """Return camera, projection, and VLA segment guidance for these tools."""
    return {
        "CAMERA AND PROJECTION RULES": Numbered(system_parts.CAMERA_AND_PROJECTION),
        "VLA SEGMENT GATES": Numbered(system_parts.VLA_GATES),
    }


__all__ = ["prompt_sections"]
