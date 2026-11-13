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

"""Assemble one model prompt from fixed, traceable layers.

Every robot contributes only its domain knowledge. Shared rules live in
``rpent/prompt/fragments``, run modes add their own contract, and the tool
surface contributes the guidance for the tools it exposes. The layer order is
fixed so a reader can predict where a rule lives:

    base -> mode -> tool families -> robot domain -> memory

Prompt rendering stays independent of the robot runtime: tool contributions are
declared by the robot's ``PromptBundle.prompt_sections`` and are pure functions
of the prompt variables. ``--dump-prompt`` therefore renders a full prompt
without starting simulators or models.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from rpent.prompt.utils import PromptNode, format_prompt
from rpent.utils.config import get_repo_root

if TYPE_CHECKING:
    from rpent.robots.prompt_bundle import PromptBundle

PromptRole = Literal["system", "user"]

_FRAGMENT_DIR = Path(__file__).with_name("fragments")

#: How each planner receives the two prompt roles.
#:
#: ``api`` keeps the system prompt separate. ``claude_code`` and ``codex``
#: prepend the system prompt to the first user message; recording that layout
#: keeps ``prompt_sources.json`` honest about what the model actually saw.
PLANNER_PROMPT_LAYOUT: dict[str, str] = {
    "api": "separate_system",
    "claude_code": "system_prefixed_to_user",
    "codex": "system_prefixed_to_user",
    "flash": "not_applicable",
}

_MODES: dict[str, tuple[str, str]] = {
    "evaluate": ("mode_evaluate", "RUN MODE — EVALUATION"),
    "explore": ("mode_explore", "RUN MODE — EXPLORATION"),
    "dashboard": ("mode_dashboard", "RUN MODE — DASHBOARD"),
    "real_robot": ("mode_real_robot", "RUN MODE — REAL ROBOT"),
}


@dataclass(frozen=True)
class PromptSection:
    """One named prompt contribution and where it came from.

    ``source`` is repository-relative (for example
    ``rpent/prompt/fragments/base.md``) so ``prompt_sources.json`` can be
    checked against the tree that produced a run.
    """

    name: str
    node: PromptNode
    source: str
    role: PromptRole = "system"


def section_source(module_file: str | Path) -> str:
    """Return the repository-relative path of a prompt module.

    ``prompt_sources.json`` records one source per contribution. Prompt modules
    pass their ``__file__`` here so a section points at the file that defines
    its text, not merely at the robot's ``prompts`` directory.
    """
    path = Path(module_file).resolve()
    try:
        return path.relative_to(get_repo_root()).as_posix()
    except ValueError:
        return path.as_posix()


def sections(
    module_file: str | Path,
    node: Mapping[str, PromptNode] | PromptNode,
    *,
    role: PromptRole = "system",
) -> tuple[PromptSection, ...]:
    """Name every contribution in ``node`` and attribute it to ``module_file``."""
    source = section_source(module_file)
    if isinstance(node, Mapping):
        return tuple(
            PromptSection(str(name), {str(name): body}, source=source, role=role)
            for name, body in node.items()
        )
    return (PromptSection("ROBOT" if role == "system" else "TASK", node, source, role),)


@dataclass(frozen=True)
class PromptLayers:
    """Contributions grouped by the fixed assembly layers.

    Each layer is ordered; the group order is enforced by
    :func:`assemble_prompt`, not by the robot.
    """

    base: Sequence[PromptSection] = field(default_factory=tuple)
    mode: Sequence[PromptSection] = field(default_factory=tuple)
    tools: Sequence[PromptSection] = field(default_factory=tuple)
    domain: Sequence[PromptSection] = field(default_factory=tuple)
    memory: Sequence[PromptSection] = field(default_factory=tuple)

    def ordered(self) -> Iterator[PromptSection]:
        """Yield sections in the fixed layer order."""
        for layer in (self.base, self.mode, self.tools, self.domain, self.memory):
            yield from layer


@dataclass(frozen=True)
class AssembledPrompt:
    """Rendered prompts plus the provenance recorded for this run."""

    system: str
    user: str
    prompt_sha256: str
    sections: tuple[dict[str, Any], ...]


@lru_cache(maxsize=None)
def _fragment_text(stem: str) -> str:
    path = _FRAGMENT_DIR / f"{stem}.md"
    return path.read_text(encoding="utf-8")


def fragment(stem: str, title: str, *, role: PromptRole = "system") -> PromptSection:
    """Load one shared fragment as a named prompt section.

    Args:
        stem: Fragment file stem under ``rpent/prompt/fragments``.
        title: Section heading shown to the model.
        role: Whether the fragment belongs to the system or user prompt.

    Returns:
        The section with its repository-relative source path.
    """
    return PromptSection(
        name=title,
        node={title: _fragment_text(stem)},
        source=f"rpent/prompt/fragments/{stem}.md",
        role=role,
    )


def mode_sections(modes: Sequence[str]) -> tuple[PromptSection, ...]:
    """Return the mode fragments for one run, in the declared order.

    Unknown mode names are rejected: a typo must not silently drop the contract
    for a run mode.
    """
    sections: list[PromptSection] = []
    seen: set[str] = set()
    for mode in modes:
        if mode in seen:
            continue
        seen.add(mode)
        try:
            stem, title = _MODES[mode]
        except KeyError as exc:
            raise ValueError(f"unknown prompt mode: {mode!r}") from exc
        sections.append(fragment(stem, title))
    return tuple(sections)


def run_modes(*, explore: bool, dashboard: bool, real_robot: bool) -> tuple[str, ...]:
    """Compose the run modes that apply to one session."""
    modes = ["explore" if explore else "evaluate"]
    if dashboard:
        modes.append("dashboard")
    if real_robot:
        modes.append("real_robot")
    return tuple(modes)


def memory_sections(
    variables: Mapping[str, object], *, explore: bool
) -> tuple[PromptSection, ...]:
    """Return memory guidance this run can actually use.

    Reading is described only when the corpus directory exists; a path string
    alone would still make the model list a directory that is not there. The
    proposal contract applies whenever exploration can write to its inbox,
    including a first exploration run that has no corpus yet.
    """
    memory_dir = variables.get("memory_dir")
    has_corpus = bool(memory_dir) and Path(str(memory_dir)).is_dir()
    sections = []
    if has_corpus:
        sections.append(fragment("memory_protocol", "MEMORY — HOW TO READ"))
        sections.append(fragment("memory_transfer", "MEMORY — USING STORED EVIDENCE"))
    if explore:
        sections.append(fragment("memory_proposals", "MEMORY — PROPOSALS AND MERGING"))
    return tuple(sections)


def build_robot_prompt(
    bundle: "PromptBundle",
    *,
    robot_name: str,
    variables: Mapping[str, object],
    modes: Sequence[str],
) -> AssembledPrompt:
    """Assemble one robot's system and user prompts.

    Args:
        bundle: The robot's domain prompt factories and optional tool sections.
        robot_name: Registry name, used as the default source label.
        variables: Prompt variables passed to every contribution.
        modes: Run modes such as ``("evaluate", "real_robot")``.

    Returns:
        The rendered prompts, combined digest, and per-section provenance.
    """
    source = bundle.source or f"robots/{robot_name}/prompt_bundle.py"
    tools = (
        bundle.prompt_sections(variables) if bundle.prompt_sections is not None else ()
    )
    layers = PromptLayers(
        base=(fragment("base", "OPERATING RULES"),),
        mode=mode_sections(modes),
        tools=_normalize(tools, source=source, role="system"),
        domain=_normalize(bundle.system(variables), source=source, role="system"),
        memory=memory_sections(variables, explore="explore" in modes),
    )
    user = _normalize(bundle.user(variables), source=source, role="user")
    return assemble_prompt(layers, user=user, variables=variables)


def assemble_prompt(
    layers: PromptLayers,
    *,
    user: Sequence[PromptSection] = (),
    variables: Mapping[str, object] | None = None,
) -> AssembledPrompt:
    """Render the fixed layers and record the source of every rendered section.

    Sections that render to an empty string are dropped from both the prompt and
    the provenance list: a conditional contribution the model never saw must not
    appear in ``prompt_sources.json``.

    Args:
        layers: System-prompt contributions grouped by layer.
        user: User-message contributions.
        variables: Strict template variables shared by every section.

    Returns:
        Rendered system and user prompts with a combined SHA-256 digest.

    Raises:
        ValueError: If two sections in the same role share a name, which would
            otherwise silently drop one of them.
    """
    grouped: dict[PromptRole, list[PromptSection]] = {
        "system": list(layers.ordered()),
        "user": list(user),
    }
    rendered: dict[PromptRole, str] = {}
    sources: list[dict[str, Any]] = []
    for role, sections in grouped.items():
        seen: set[str] = set()
        parts: list[str] = []
        for section in sections:
            if section.role != role:
                raise ValueError(
                    f"section {section.name!r} declares role {section.role!r} "
                    f"but was placed in the {role} prompt"
                )
            if section.name in seen:
                raise ValueError(
                    f"duplicate prompt section {section.name!r} in the {role} prompt"
                )
            seen.add(section.name)
            text = format_prompt(section.node, variables=variables).rstrip("\n")
            if not text.strip():
                # A conditional contribution that rendered to nothing is not
                # part of the prompt; recording it would claim a section the
                # model never saw.
                continue
            parts.append(text)
            sources.append(
                {
                    "name": section.name,
                    "role": role,
                    "source": section.source,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
        rendered[role] = "\n\n\n".join(parts)
        if rendered[role]:
            rendered[role] += "\n"

    digest = hashlib.sha256(
        f"system\0{rendered['system']}\0user\0{rendered['user']}".encode("utf-8")
    ).hexdigest()
    return AssembledPrompt(
        system=rendered["system"],
        user=rendered["user"],
        prompt_sha256=digest,
        sections=tuple(sources),
    )


def _normalize(
    node: PromptNode | Sequence[PromptSection],
    *,
    source: str,
    role: PromptRole,
) -> tuple[PromptSection, ...]:
    """Turn a contribution into named sections without changing its content."""
    if isinstance(node, PromptSection):
        return (node,)
    if isinstance(node, Mapping):
        return tuple(
            PromptSection(
                name=str(name), node={str(name): body}, source=source, role=role
            )
            for name, body in node.items()
        )
    if isinstance(node, Iterable) and not isinstance(node, (str, bytes)):
        sections = list(node)
        if all(isinstance(section, PromptSection) for section in sections):
            return tuple(sections)
    name = "USER" if role == "user" else "ROBOT"
    return (PromptSection(name=name, node=node, source=source, role=role),)


def prompt_sha256(system: str, user: str) -> str:
    """Return the digest of the assembled system and user prompts.

    This is the digest of the two roles as assembled, not necessarily of the
    single message a planner receives. Use
    :func:`rpent.prompt.artifacts.delivered_prompt_sha256` for that layout.
    """
    return hashlib.sha256(f"system\0{system}\0user\0{user}".encode("utf-8")).hexdigest()
