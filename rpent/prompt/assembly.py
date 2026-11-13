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
``rpent/prompt/fragments``, the run axes add their own contract, and the tool
families contribute the guidance for the tools they expose. A slice may still
contribute guidance for tools that exist only in that robot through
``PromptBundle.tool_sections``; it must not restate a family's tool. The layer
order is fixed so a reader can predict where a rule lives:

    base -> run axes -> tool families -> robot domain -> memory

Prompt rendering stays independent of the robot runtime: tool contributions are
pure functions of the prompt variables. ``--dump-prompt`` therefore renders a
full prompt without starting simulators or models.

:data:`PLANNER_PROMPT_LAYOUT` and :func:`prefix_system_prompt` describe how a
planner frames the two roles. The planners call the same helper so the recorded
layout and the delivered text cannot drift apart.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from rpent.prompt.utils import SECTION_SEPARATOR, PromptNode, format_prompt
from rpent.utils.config import get_repo_root

if TYPE_CHECKING:
    from rpent.robots.prompt_bundle import PromptBundle

PromptRole = Literal["system", "user"]

_FRAGMENT_DIR = Path(__file__).with_name("fragments")

#: How each planner receives the two prompt roles.
#:
#: ``api`` and ``claude_code`` keep the system prompt separate; the Claude Code
#: planner appends RPent's rules to the SDK's ``claude_code`` preset, so they
#: stay a system message. ``codex`` has no system-prompt option and prepends the
#: system prompt to the first user message. Recording the layout keeps
#: ``prompt_sources.json`` honest about what the model actually saw.
PLANNER_PROMPT_LAYOUT: dict[str, str] = {
    "api": "separate_system",
    "claude_code": "separate_system",
    "codex": "system_prefixed_to_user",
    "flash": "not_applicable",
}

_AXES: dict[str, tuple[str, str]] = {
    "evaluate": ("mode_evaluate", "RUN MODE — EVALUATION"),
    "explore": ("mode_explore", "RUN MODE — EXPLORATION"),
    "interactive": ("interactive", "RUN MODE — INTERACTIVE"),
    "real_robot": ("real_robot", "RUN MODE — REAL ROBOT"),
}


def prefix_system_prompt(system: str, user: str) -> str:
    """Return the single message a planner sends when it cannot separate roles.

    Codex prepends the system prompt to the first user message because its
    thread options have no system role. The planner and
    :mod:`rpent.prompt.prompt_artifacts` call this helper so the delivered text
    has one implementation.
    """
    return f"{system}\n\n{user}" if system else user


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

    An installed distribution may place the module outside the repository root
    that :func:`get_repo_root` derives, so fall back to the directory above the
    module's outermost package.
    """
    path = Path(module_file).resolve()
    try:
        return path.relative_to(get_repo_root()).as_posix()
    except ValueError:
        return path.relative_to(_package_root(path)).as_posix()


def _package_root(path: Path) -> Path:
    """Return the directory containing the outermost package of ``path``."""
    for parent in path.parents:
        if not (parent / "__init__.py").is_file():
            return parent
    return path.parent


def sections(
    module_file: str | Path,
    node: Mapping[str, PromptNode] | PromptNode,
    *,
    role: PromptRole = "system",
) -> tuple[PromptSection, ...]:
    """Name every contribution in ``node`` and attribute it to ``module_file``."""
    return _named_sections(node, source=section_source(module_file), role=role)


def _named_sections(
    node: Mapping[str, PromptNode] | PromptNode,
    *,
    source: str,
    role: PromptRole,
) -> tuple[PromptSection, ...]:
    """Split one contribution into named sections attributed to ``source``."""
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
    axis: Sequence[PromptSection] = field(default_factory=tuple)
    tools: Sequence[PromptSection] = field(default_factory=tuple)
    domain: Sequence[PromptSection] = field(default_factory=tuple)
    memory: Sequence[PromptSection] = field(default_factory=tuple)

    def ordered(self) -> Iterator[PromptSection]:
        """Yield sections in the fixed layer order."""
        for layer in (self.base, self.axis, self.tools, self.domain, self.memory):
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


def _axis_sections(axes: Sequence[str]) -> tuple[PromptSection, ...]:
    """Return the fragments for the run axes that apply, in declared order.

    Unknown axis names are rejected: a typo must not silently drop the contract
    for a run axis.
    """
    sections: list[PromptSection] = []
    seen: set[str] = set()
    for axis in axes:
        if axis in seen:
            continue
        seen.add(axis)
        try:
            stem, title = _AXES[axis]
        except KeyError as exc:
            raise ValueError(f"unknown prompt axis: {axis!r}") from exc
        sections.append(fragment(stem, title))
    return tuple(sections)


def run_axes(*, explore: bool, dashboard: bool, real_robot: bool) -> tuple[str, ...]:
    """Compose the run axes that apply to one session.

    ``dashboard`` selects the interactive axis; the Dashboard is its current
    implementation, not a separate axis. ``policy_mode`` is the fourth axis in
    ``a_global`` 2.2 and is added by a_4 together with its ``mode_code``
    fragment; until that lands, this helper must not invent code-mode rules.
    """
    axes = ["explore" if explore else "evaluate"]
    if dashboard:
        axes.append("interactive")
    if real_robot:
        axes.append("real_robot")
    return tuple(axes)


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
    axes: Sequence[str],
) -> AssembledPrompt:
    """Assemble one robot's system and user prompts.

    Args:
        bundle: The robot's domain prompt factories and optional guidance for
            tools that exist only in this slice. Shared tool usage comes from
            the tool families (a_3); a bundle with no ``tool_sections`` is
            valid.
        robot_name: Registry name, used as the default source label.
        variables: Prompt variables passed to every contribution.
        axes: Run axes that apply, such as ``("evaluate", "real_robot")``.

    Returns:
        The rendered prompts, combined digest, and per-section provenance.
    """
    source = bundle.source or f"robots/{robot_name}/prompt_bundle.py"
    tools = bundle.tool_sections(variables) if bundle.tool_sections is not None else ()
    layers = PromptLayers(
        base=(fragment("base", "OPERATING RULES"),),
        axis=_axis_sections(axes),
        tools=_normalize(tools, source=source, role="system"),
        domain=_normalize(bundle.system(variables), source=source, role="system"),
        memory=memory_sections(variables, explore="explore" in axes),
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
        rendered[role] = SECTION_SEPARATOR.join(parts)
        if rendered[role]:
            rendered[role] += "\n"

    return AssembledPrompt(
        system=rendered["system"],
        user=rendered["user"],
        prompt_sha256=prompt_sha256(rendered["system"], rendered["user"]),
        sections=tuple(sources),
    )


def _normalize(
    node: PromptNode | Sequence[PromptSection],
    *,
    source: str,
    role: PromptRole,
) -> tuple[PromptSection, ...]:
    """Turn a contribution into named sections without changing its content."""
    if isinstance(node, Iterable) and not isinstance(node, (str, bytes)):
        parts = list(node)
        if all(isinstance(part, PromptSection) for part in parts):
            return tuple(parts)
    elif isinstance(node, PromptSection):
        return (node,)
    return _named_sections(node, source=source, role=role)


def prompt_sha256(system: str, user: str) -> str:
    """Return the digest of the assembled system and user prompts.

    This is the digest of the two roles as assembled, not necessarily of the
    single message a planner receives. ``prompt_sources.json`` records the
    planner layout separately, and ``effective_prompt.md`` contains the exact
    text a prefixing planner sends.
    """
    return hashlib.sha256(f"system\0{system}\0user\0{user}".encode("utf-8")).hexdigest()
