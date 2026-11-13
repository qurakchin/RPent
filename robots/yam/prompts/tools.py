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

from robots.yam.prompts import system as system_parts
from rpent.prompt.utils import PromptNode


def prompt_sections(
    variables: Mapping[str, object] | None = None,
) -> Mapping[str, PromptNode]:
    """Return perception, control, and policy guidance for the exposed tools."""
    policy = (
        system_parts.VLA
        if (variables or {}).get("vla_enabled", False)
        else system_parts.PRIMITIVES_ONLY
    )
    return {
        "PERCEPTION": system_parts.PERCEPTION,
        "CONTROL": system_parts.CONTROL,
        "POLICY AVAILABILITY": policy,
    }


__all__ = ["prompt_sections"]
