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

from collections.abc import Mapping, Sequence
from pathlib import Path

from rpent.prompt.assembly import (
    PLANNER_PROMPT_LAYOUT,
    AssembledPrompt,
    prefix_system_prompt,
)
from rpent.utils.files import write_json_atomic, write_text_atomic

EFFECTIVE_PROMPT = "effective_prompt.md"
PROMPT_SOURCES = "prompt_sources.json"


def delivered_prompt_text(planner: str, *, system: str, user: str) -> str | None:
    """Return the single message a prefixing planner delivers, if there is one.

    ``system_prefixed_to_user`` planners concatenate the system prompt and the
    user message with :func:`~rpent.prompt.assembly.prefix_system_prompt`, which
    is the same helper the planners call. ``separate_system`` planners send two
    messages, so there is no single delivered text; ``not_applicable`` planners
    ignore the prompt entirely.
    """
    if PLANNER_PROMPT_LAYOUT.get(planner, "unknown") != "system_prefixed_to_user":
        return None
    return prefix_system_prompt(system, user)


def write_prompt_artifacts(
    directory: Path,
    *,
    assembled: AssembledPrompt,
    robot_name: str,
    planner: str,
    axes: Sequence[str],
    user_message: str,
) -> tuple[Path, Path]:
    """Write ``effective_prompt.md`` and ``prompt_sources.json``.

    Args:
        directory: Run or session output directory.
        assembled: Rendered prompts and section provenance.
        robot_name: Robot registry name.
        planner: Planner name recorded with the prompt.
        axes: Run axes that shaped this prompt.
        user_message: The exact opening message handed to the planner.

    Returns:
        Paths of the prompt and sources files.
    """
    directory.mkdir(parents=True, exist_ok=True)
    prompt_path = write_text_atomic(
        directory / EFFECTIVE_PROMPT,
        effective_prompt_markdown(
            assembled,
            robot_name=robot_name,
            planner=planner,
            axes=axes,
            user_message=user_message,
        ),
    )
    sources_path = write_json_atomic(
        directory / PROMPT_SOURCES,
        prompt_sources(
            assembled,
            robot_name=robot_name,
            planner=planner,
            axes=axes,
        ),
        ensure_ascii=False,
    )
    return prompt_path, sources_path


def effective_prompt_markdown(
    assembled: AssembledPrompt,
    *,
    robot_name: str,
    planner: str,
    axes: Sequence[str],
    user_message: str,
) -> str:
    """Render the prompt artifact for humans."""
    layout = PLANNER_PROMPT_LAYOUT.get(planner, "unknown")
    header = [
        "# Effective prompt",
        "",
        f"- robot: `{robot_name}`",
        f"- planner: `{planner}` ({layout})",
        f"- axes: {', '.join(f'`{axis}`' for axis in axes)}",
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
    delivered = delivered_prompt_text(
        planner, system=assembled.system, user=user_message
    )
    if delivered is not None:
        header.extend(
            [
                "## Delivered prompt",
                "",
                "This planner sends the two layers as one message:",
                "",
                delivered.rstrip("\n"),
                "",
            ]
        )
    return "\n".join(header)


def prompt_sources(
    assembled: AssembledPrompt,
    *,
    robot_name: str,
    planner: str,
    axes: Sequence[str],
) -> Mapping[str, object]:
    """Build the machine-readable prompt provenance record.

    ``prompt_sha256`` covers the assembled system and robot user prompt.
    ``planner_prompt_layout`` records how the planner frames the two roles, and
    ``effective_prompt.md`` contains the delivered text for prefixing planners,
    so a second digest of the same text is not recorded.
    """
    return {
        "robot": robot_name,
        "planner": planner,
        "planner_prompt_layout": PLANNER_PROMPT_LAYOUT.get(planner, "unknown"),
        "axes": list(axes),
        "prompt_sha256": assembled.prompt_sha256,
        "sections": list(assembled.sections),
    }
