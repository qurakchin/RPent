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

"""RoboTwin prompt bundle assembly."""

from __future__ import annotations

from collections.abc import Mapping

from robots.robotwin.prompts import evaluate as evaluate_parts
from robots.robotwin.prompts import explore as explore_parts
from robots.robotwin.prompts import tools as tool_parts
from robots.robotwin.prompts import user as user_parts
from rpent.prompt.assembly import PromptSection, sections
from rpent.prompt.utils import PromptNode


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> PromptNode:
    """Return the RoboTwin system prompt for the selected run mode."""
    variables = variables or {}
    if (
        variables.get("mode", "eval") == "explore"
        and variables.get("policy_kind") != "wam"
    ):
        return explore_parts.system_prompt()
    return evaluate_parts.system_prompt(variables)


def user_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    if (variables or {}).get("policy_kind") == "wam":
        return sections(
            user_parts.__file__,
            {"TASK": user_parts.WAM_TASK, "MEMORY": user_parts.WAM_MEMORY},
            role="user",
        )
    prompt = {
        "CELL": user_parts.CELL,
        "BEGIN": user_parts.BEGIN,
    }
    if (variables or {}).get("mode", "eval") == "explore":
        prompt["EXPLORE MODE"] = explore_parts.USER_MODE
    return sections(user_parts.__file__, prompt, role="user")


__all__ = ["system_prompt", "user_prompt", "tool_sections"]


def tool_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the RoboTwin tool guidance for the selected policy."""
    return tool_parts.tool_sections(variables)
