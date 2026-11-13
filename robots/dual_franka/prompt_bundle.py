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

"""Prompt bundle assembly for the dual-Franka environment."""

from __future__ import annotations

from collections.abc import Mapping

from robots.dual_franka.prompts import explore as explore_parts
from robots.dual_franka.prompts import system as system_parts
from robots.dual_franka.prompts import tools as tool_parts
from robots.dual_franka.prompts import user as user_parts
from rpent.prompt.assembly import PromptSection, section_source, sections
from rpent.prompt.utils import Numbered


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Assemble the dual-Franka system prompt."""
    if (variables or {}).get("mode") == "explore":
        return explore_parts.system_prompt()
    return sections(
        system_parts.__file__,
        {
            "ROLE": system_parts.ROLE,
            "RUNTIME": system_parts.RUNTIME,
            "SAFETY RULES": Numbered(system_parts.RULES),
            "WORKFLOW": Numbered(system_parts.WORKFLOW),
        },
    )


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the dual-Franka tool guidance for the tools layer."""
    return tool_parts.prompt_sections(variables)


def user_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Assemble the task-specific initial user prompt."""
    explore = (variables or {}).get("mode") == "explore"
    begin = explore_parts.BEGIN if explore else user_parts.BEGIN
    begin_source = explore_parts.__file__ if explore else user_parts.__file__
    prompt = (
        *sections(
            user_parts.__file__,
            {"TASK": user_parts.TASK, "TASK CONSTRAINTS": user_parts.CONSTRAINTS},
            role="user",
        ),
        PromptSection("BEGIN", {"BEGIN": begin}, section_source(begin_source), "user"),
    )
    if explore:
        prompt = (
            *prompt,
            PromptSection(
                "EXPLORATION OUTPUT",
                {
                    "EXPLORATION OUTPUT": (
                        "Use {{memory_inbox}} for reviewable exploration notes and "
                        "{{output_dir}}/attempts/ for failed-attempt archives."
                    )
                },
                section_source(__file__),
                "user",
            ),
        )
    return prompt
