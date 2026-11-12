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

"""Write the prompt a run actually used, next to its other artifacts.

``effective_prompt.md`` answers "what did the model see"; ``prompt_sources.json``
records which file and layer each section came from, plus how the planner
delivered the system prompt. Both are written per session so exploration
handoffs do not overwrite each other's evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from rpent.prompt.assembly import PLANNER_PROMPT_LAYOUT, AssembledPrompt

EFFECTIVE_PROMPT = "effective_prompt.md"
PROMPT_SOURCES = "prompt_sources.json"


def write_prompt_artifacts(
    directory: Path,
    *,
    assembled: AssembledPrompt,
    robot_name: str,
    planner: str,
    modes: Sequence[str],
    user_message: str,
) -> tuple[Path, Path]:
    """Write ``effective_prompt.md`` and ``prompt_sources.json``.

    Args:
        directory: Run or session output directory.
        assembled: Rendered prompts and section provenance.
        robot_name: Robot registry name.
        planner: Planner name recorded with the prompt.
        modes: Run modes that shaped this prompt.
        user_message: The exact opening message handed to the planner.

    Returns:
        Paths of the prompt and sources files.
    """
    directory.mkdir(parents=True, exist_ok=True)
    prompt_path = directory / EFFECTIVE_PROMPT
    sources_path = directory / PROMPT_SOURCES
    prompt_path.write_text(
        effective_prompt_markdown(
            assembled,
            robot_name=robot_name,
            planner=planner,
            modes=modes,
            user_message=user_message,
        ),
        encoding="utf-8",
    )
    sources_path.write_text(
        json.dumps(
            prompt_sources(
                assembled,
                robot_name=robot_name,
                planner=planner,
                modes=modes,
                user_message=user_message,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return prompt_path, sources_path


def effective_prompt_markdown(
    assembled: AssembledPrompt,
    *,
    robot_name: str,
    planner: str,
    modes: Sequence[str],
    user_message: str,
) -> str:
    """Render the prompt artifact for humans."""
    layout = PLANNER_PROMPT_LAYOUT.get(planner, "unknown")
    header = [
        "# Effective prompt",
        "",
        f"- robot: `{robot_name}`",
        f"- planner: `{planner}` ({layout})",
        f"- modes: {', '.join(f'`{mode}`' for mode in modes)}",
        f"- prompt_sha256: `{assembled.prompt_sha256}`",
        "",
        "## System prompt",
        "",
        assembled.system.rstrip("\n"),
        "",
        "## User message",
        "",
        user_message.rstrip("\n"),
        "",
    ]
    return "\n".join(header)


def prompt_sources(
    assembled: AssembledPrompt,
    *,
    robot_name: str,
    planner: str,
    modes: Sequence[str],
    user_message: str,
) -> Mapping[str, object]:
    """Build the machine-readable prompt provenance record.

    ``prompt_sha256`` covers the assembled system and robot user prompt;
    ``user_message_sha256`` covers the opening message actually delivered,
    which a continuation session replaces with its handoff text.
    """
    return {
        "robot": robot_name,
        "planner": planner,
        "planner_prompt_layout": PLANNER_PROMPT_LAYOUT.get(planner, "unknown"),
        "modes": list(modes),
        "prompt_sha256": assembled.prompt_sha256,
        "user_message_sha256": hashlib.sha256(user_message.encode("utf-8")).hexdigest(),
        "sections": list(assembled.sections),
    }
