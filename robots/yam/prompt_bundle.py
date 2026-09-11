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

"""YAM prompt bundle assembly."""

from __future__ import annotations

from collections.abc import Mapping

from robots.yam.prompts import system as system_parts
from robots.yam.prompts import user as user_parts
from rpent.prompt.utils import PromptNode


def system_prompt(variables: Mapping[str, object] | None = None) -> PromptNode:
    policy = (
        system_parts.VLA
        if (variables or {}).get("vla_enabled", False)
        else system_parts.PRIMITIVES_ONLY
    )
    if (variables or {}).get("mode", "eval") == "explore":
        return {
            "ROLE": system_parts.ROLE,
            "READ ORDER": system_parts.READ_ORDER,
            "REAL-ROBOT EXPLORE": system_parts.EXPLORE,
            "RUNTIME": system_parts.RUNTIME,
            "PERCEPTION": system_parts.PERCEPTION,
            "CONTROL": system_parts.CONTROL,
            "POLICY AVAILABILITY": policy,
            "SUCCESS": system_parts.SUCCESS,
        }
    return {
        "ROLE": system_parts.ROLE,
        "READ ORDER": system_parts.READ_ORDER,
        "RUNTIME": system_parts.RUNTIME,
        "PERCEPTION": system_parts.PERCEPTION,
        "CONTROL": system_parts.CONTROL,
        "POLICY AVAILABILITY": policy,
        "SUCCESS": system_parts.SUCCESS,
    }


def user_prompt(variables: Mapping[str, object] | None = None) -> PromptNode:
    return {"CELL": user_parts.CELL, "BEGIN": user_parts.BEGIN}


__all__ = ["system_prompt", "user_prompt"]
