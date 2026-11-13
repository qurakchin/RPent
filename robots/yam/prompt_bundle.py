# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""YAM prompt bundle assembly."""

from __future__ import annotations

from collections.abc import Mapping

from robots.yam.prompts import system as system_parts
from robots.yam.prompts import tools as tool_parts
from robots.yam.prompts import user as user_parts
from rpent.prompt.assembly import PromptSection, sections


def system_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    node = {
        "ROLE": system_parts.ROLE,
        "READ ORDER": system_parts.READ_ORDER,
        **(
            {"REAL-ROBOT EXPLORE": system_parts.EXPLORE}
            if (variables or {}).get("mode", "eval") == "explore"
            else {}
        ),
        "RUNTIME": system_parts.RUNTIME,
        "SUCCESS": system_parts.SUCCESS,
    }
    return sections(system_parts.__file__, node)


def user_prompt(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    return sections(
        user_parts.__file__,
        {"CELL": user_parts.CELL, "BEGIN": user_parts.BEGIN},
        role="user",
    )


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> tuple[PromptSection, ...]:
    """Return the YAM tool guidance for the tools layer."""
    return tool_parts.prompt_sections(variables)


__all__ = ["system_prompt", "user_prompt", "prompt_sections"]
