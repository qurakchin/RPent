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

from rpent.prompt.assembly import (
    PLANNER_PROMPT_LAYOUT,
    AssembledPrompt,
    prompt_sha256,
)

EFFECTIVE_PROMPT = "effective_prompt.md"
PROMPT_SOURCES = "prompt_sources.json"


def delivered_prompt_text(planner: str, *, system: str, user: str) -> str | None:
    """Return the single message a prefixing planner delivers, if there is one.

    ``system_prefixed_to_user`` planners concatenate the system prompt and the
    user message into one string before sending it. ``separate_system``
    planners send two messages, so their delivery is
    :func:`~rpent.prompt.assembly.prompt_sha256` rather than one text;
    ``not_applicable`` planners ignore the prompt entirely.
    """
    if PLANNER_PROMPT_LAYOUT.get(planner, "unknown") != "system_prefixed_to_user":
        return None
    return f"{system}\n\n{user}" if system else user


def delivered_prompt_sha256(planner: str, *, system: str, user: str) -> str | None:
    """Return the digest of the text the planner actually hands to the model.

    For ``separate_system`` planners this is the two-message digest from
    :func:`prompt_sha256`; for prefixing planners it covers the concatenated
    message; for planners that ignore the prompt it is ``None``.
    """
    layout = PLANNER_PROMPT_LAYOUT.get(planner, "unknown")
    if layout == "not_applicable":
        return None
    if layout == "system_prefixed_to_user":
        delivered = delivered_prompt_text(planner, system=system, user=user) or ""
        return hashlib.sha256(delivered.encode("utf-8")).hexdigest()
    return prompt_sha256(system, user)


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
    delivered_sha = delivered_prompt_sha256(
        planner, system=assembled.system, user=user_message
    )
    header = [
        "# Effective prompt",
        "",
        f"- robot: `{robot_name}`",
        f"- planner: `{planner}` ({layout})",
        f"- modes: {', '.join(f'`{mode}`' for mode in modes)}",
        f"- prompt_sha256: `{assembled.prompt_sha256}`",
        f"- delivered_prompt_sha256: `{delivered_sha or 'not delivered'}`",
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
    modes: Sequence[str],
    user_message: str,
) -> Mapping[str, object]:
    """Build the machine-readable prompt provenance record.

    ``prompt_sha256`` covers the assembled system and robot user prompt;
    ``delivered_prompt_sha256`` covers the exact text the planner hands to the
    model after its own framing (``None`` when the planner ignores the prompt);
    ``user_message_sha256`` covers the opening message actually delivered,
    which a continuation session replaces with its handoff text.
    """
    return {
        "robot": robot_name,
        "planner": planner,
        "planner_prompt_layout": PLANNER_PROMPT_LAYOUT.get(planner, "unknown"),
        "modes": list(modes),
        "prompt_sha256": assembled.prompt_sha256,
        "delivered_prompt_sha256": delivered_prompt_sha256(
            planner, system=assembled.system, user=user_message
        ),
        "user_message_sha256": hashlib.sha256(user_message.encode("utf-8")).hexdigest(),
        "sections": list(assembled.sections),
    }
