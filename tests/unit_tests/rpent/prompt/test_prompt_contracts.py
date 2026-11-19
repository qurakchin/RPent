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

"""Contracts for the migrated prompt sources.

The shared-fragment migration moved common rules into
``rpent/prompt/fragments``. These checks keep the model-facing instructions
consistent with the shared sources and the memory manager:

- a robot's ``tool_sections`` supplies the tool guidance for that slice and
  may be omitted when the slice adds none;
- prompts name tools without restating their call signatures;
- no prompt asks for ``corroborations.jsonl`` or ``conflict_<id>.md``, which
  the merge step does not consume;
- proposals use a bare ``id`` in both scopes;
- a deleted per-robot reminder stays covered by a shared or robot-local rule.
  For example, the dual-Franka VLA segment stop is covered by
  ``VLA SEGMENT GATES`` and the single-attempt rules by ``base.md``.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from rpent.prompt.assembly import (
    PromptSection,
    build_robot_prompt,
    fragment,
    run_axes,
)
from rpent.prompt.utils import format_prompt
from rpent.robots import get_robot_spec
from rpent.robots.prompt_bundle import PromptBundle
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

ROOT = Path(__file__).resolve().parents[4]
#: Aggregate source ceiling at the measured total, including the section
#: mappings and formatting that never reach the model. The per-slice ceilings
#: below carry 5% headroom, so this aggregate is what forbids net growth: a
#: slice may grow only by consuming another slice's reduction. The model-facing
#: bound is :data:`PROMPT_SLICE_RENDERED_BUDGET`.
#: The merged tree adds the tool-result vocabulary ``a_3`` gives the slices
#: that emit motion results: RoboTwin's stop fields and RoboDojo's stop reasons.
PROMPT_SOURCE_LINE_BUDGET = 2414
#: Design target for slice-owned prompt source (``a_2`` §7): the hand-written
#: slice prompts together, including the code-mode prompts ``a_4`` adds. This
#: branch counts ``robots/<robot>/prompts/*.py`` plus ``prompt_bundle.py``
#: without those prompts, so comparing the smaller set to the target is
#: conservative. The strict xfail below records the gap.
PROMPT_SOURCE_LINE_TARGET = 1200
#: Per-slice source ceiling: the measured count plus 5%, rounded up. The
#: headroom lets a slice take over another's reduction without editing two
#: constants, while :data:`PROMPT_SOURCE_LINE_BUDGET` still forbids net growth.
PROMPT_SLICE_LINE_BUDGET = {
    "libero": 888,
    "robodojo": 456,
    "robocasa": 324,
    "dual_franka": 281,
    "robotwin": 294,
    "yam": 214,
    "franka": 75,
}

#: Acceptances that describe what the model reads, in rendered lines: the
#: LIBERO domain is a broad benchmark family, the other slices are narrower.
PROMPT_DOMAIN_RENDERED_TARGET = {"libero": 300, "other": 150}
#: Rendered slice text (domain, tool usage, user message) each robot may ship:
#: the measured count plus 5%, rounded up. The headroom has the same trade role
#: as :data:`PROMPT_SLICE_LINE_BUDGET`, and
#: :data:`PROMPT_SLICE_RENDERED_TOTAL_BUDGET` still forbids net growth. The
#: shared tool guidance ``a_3`` adds is what removes the remaining slice tool
#: text.
PROMPT_SLICE_RENDERED_BUDGET = {
    "libero": 503,
    "robodojo": 269,
    "robocasa": 187,
    "dual_franka": 103,
    "robotwin": 179,
    "yam": 118,
    "franka": 46,
}
#: Rendered slice text in exploration mode: the measured count plus 5%, rounded
#: up. The evaluation ceilings above do not cover the exploration workflow,
#: which is the larger of the two for every slice, so each slice that reaches
#: exploration needs its own ceiling. ``franka`` does not support exploration
#: and has no entry; the key set is checked against the robot specs so a new
#: exploration-capable slice cannot skip its ceiling.
PROMPT_EXPLORE_SLICE_RENDERED_BUDGET = {
    "libero": 654,
    "robodojo": 325,
    "robocasa": 192,
    "robotwin": 209,
    "yam": 187,
    "dual_franka": 174,
}
#: Aggregate exploration ceiling at the measured total, with the same role as
#: :data:`PROMPT_SLICE_RENDERED_TOTAL_BUDGET`: it is the no-growth bound once a
#: slice uses its per-slice headroom.
PROMPT_EXPLORE_SLICE_RENDERED_TOTAL_BUDGET = 1661
#: Follow-up rendered total once shared tool guidance lands. It is not an
#: ``a_2`` design metric; the design target is the source-line count above. The
#: strict xfail below tracks it.
PROMPT_SLICE_RENDERED_TOTAL_TARGET = 1200
#: Aggregate rendered ceiling at the measured total. The per-slice ceilings
#: above carry 5% headroom, so this one binds: any net growth fails even when a
#: slice stays under its own ceiling.
PROMPT_SLICE_RENDERED_TOTAL_BUDGET = 1342

#: Tools whose call signatures must come from the tool schema, not the prompt.
TOOL_NAMES = (
    "back_project",
    "finish",
    "list_dir",
    "move_pose",
    "move_to",
    "pi0_doubled",
    "pi0_pick",
    "read_text_file",
    "release",
    "request_operator_verdict",
    "request_scene_reset",
    "rotate_pitch",
    "rotate_wrist",
    "segment",
    "set_gripper",
    "view_camera_meta",
    "view_env_state",
    "write_text_file",
)
_TOOL_CALL = re.compile(rf"\b(?:{'|'.join(TOOL_NAMES)})\(")
#: Argument names a removed call example would have restated.
TOOL_ARGUMENTS = (
    "arm",
    "camera",
    "chunks",
    "expected_scene_state",
    "gripper",
    "instruction",
    "max_chars",
    "max_chunks",
    "point",
    "prompt",
    "reason",
    "resolution",
    "status",
    "step",
    "steps",
    "success",
    "val",
    "xyz",
)
_SIGNATURE = re.compile(rf"\(\s*(?:{'|'.join(TOOL_ARGUMENTS)})\s*=\s*[\w\"'\[{{-]")
_JSON_CALL = re.compile(r"\(\s*\{")
#: An argument name followed by a literal value restates the schema even when it
#: is written as prose (``use_length=50``, ``camera='navview'``). Template
#: variables are allowed: they are filled from the run, not from the schema.
_PARAMETER_ASSIGNMENT = re.compile(
    rf"\b(?:{'|'.join(TOOL_ARGUMENTS)})\s*=\s*(?!\{{)[\w\"'-]"
)


def _prompt_source_files() -> list[Path]:
    files: list[Path] = []
    for robot in PROMPT_VARIABLES:
        directory = ROOT / "robots" / robot / "prompts"
        files.extend(
            path for path in directory.glob("*.py") if path.name != "__init__.py"
        )
        bundle = ROOT / "robots" / robot / "prompt_bundle.py"
        if bundle.is_file():
            files.append(bundle)
    return files


def _memory(tmp_path: Path) -> Path:
    memory = tmp_path / "memory"
    (memory / "global").mkdir(parents=True)
    (memory / "global/GLOBAL_MEMORY.md").write_text("# Global memory\n")
    return memory


def _render(robot: str, *, explore: bool, memory: Path, dashboard: bool = False) -> str:
    spec = get_robot_spec(robot)
    variables = {
        **PROMPT_VARIABLES[robot],
        "mode": "explore" if explore else "eval",
        "memory_dir": str(memory),
        "memory_inbox": str(memory / "_internal/inbox/cell"),
        "session_number": 1,
        "session_max": 1,
        "explore_attempts_per_session": 2,
        "output_dir": "/output",
    }
    variables.setdefault("recipe_tag", f"{robot}_cell")
    return build_robot_prompt(
        spec.prompts,
        robot_name=robot,
        variables=variables,
        axes=run_axes(
            explore=explore,
            dashboard=dashboard,
            real_robot=spec.is_real_robot,
        ),
    ).system


def _prompt_texts(memory: Path, *, explore: bool) -> dict[str, str]:
    return {
        robot: _render(robot, explore=explore, memory=memory)
        for robot in PROMPT_VARIABLES
    }


def test_a_slice_may_contribute_no_tool_sections() -> None:
    """A slice without tool guidance still contributes its domain prompt.

    Requiring every robot to define ``tool_sections`` would force empty or
    redundant guidance into a slice that only needs the base and run-axis
    rules.
    """
    bundle = PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: {"TASK": "user task"},
        tool_sections=None,
    )

    assembled = build_robot_prompt(
        bundle,
        robot_name="fixture",
        variables={},
        axes=("evaluate",),
    )

    assert "domain knowledge" in assembled.system
    assert "OPERATING RULES" in assembled.system


def test_prompts_do_not_ask_for_memory_artifacts_the_merge_cannot_consume(
    tmp_path: Path,
) -> None:
    memory = _memory(tmp_path)
    for explore in (False, True):
        for robot, text in _prompt_texts(memory, explore=explore).items():
            assert "corroborations.jsonl" not in text, (robot, explore)
            assert "conflict_<id>.md" not in text, (robot, explore)


def test_exploration_proposals_use_a_bare_id_in_both_scopes(
    tmp_path: Path,
) -> None:
    for robot, text in _prompt_texts(_memory(tmp_path), explore=True).items():
        assert "id: task-family_" not in text, robot
        assert "`id` `global_" not in text, robot
        assert "global_<kind>_<slug>" not in text, robot


def test_exploration_prompts_reuse_the_shared_mode_and_memory_contract(
    tmp_path: Path,
) -> None:
    for robot, text in _prompt_texts(_memory(tmp_path), explore=True).items():
        assert "Each attempt should test a hypothesis" in text, robot
        assert "Promote memory only after a success" in text, robot
        assert "`id` is a bare slug" in text, robot


def test_tool_signatures_are_left_to_the_tool_schema() -> None:
    """Prompt sources may name a tool but must not restate how to call it.

    The tool schema owns argument names, defaults, and call syntax. A prompt
    that repeats them drifts from the implementation and makes the model read
    two descriptions. This scans string literals, so prompt builders remain
    free to call their own helpers.
    """
    for path in _prompt_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value
            for pattern, label in (
                (_TOOL_CALL, "tool call"),
                (_SIGNATURE, "argument list"),
                (_JSON_CALL, "JSON payload"),
                (_PARAMETER_ASSIGNMENT, "parameter value"),
            ):
                match = pattern.search(text)
                assert match is None, (
                    path,
                    label,
                    text[max(0, match.start() - 40) : match.end() + 40],
                )


REMOVED_RULE_COVERAGE = (
    (
        "franka",
        "If state, cameras, or motion results disagree, stop instead of guessing.",
        ("eval", "explore"),
    ),
    (
        "franka",
        "Inspect view_env_state before motion and after every mutating tool call.",
        ("eval", "explore"),
    ),
    (
        "franka",
        "Finish only when the success evidence is visible and consistent with state.",
        ("eval", "explore"),
    ),
    (
        "dual_franka",
        "configured inline camera view(s) as the primary visual source of truth",
        ("eval", "explore"),
    ),
    (
        "dual_franka",
        "These boundaries only mean a segment ended; verify physical success",
        ("eval", "explore"),
    ),
    (
        "dual_franka",
        "call request_scene_reset with the reason and expected scene state",
        ("explore",),
    ),
    (
        "dual_franka",
        "Finish only when the success evidence is visible and consistent with state.",
        ("eval", "explore"),
    ),
    (
        "libero",
        "Write ONLY under",
        ("explore",),
    ),
)


#: Removed robot lines whose behavior now lives in ``base.md``. The replacement
#: phrases are the shared rules the model actually reads.
SHARED_RULE_COVERAGE = (
    (
        "Use small purposeful corrections and compare both camera views.",
        ("Change one thing at a time.", "Observe before acting."),
    ),
    (
        "Execute one bounded correction at a time and inspect the result.",
        ("call one tool at a time", "read each result before deciding again"),
    ),
)


def test_removed_robot_lines_are_covered_by_the_shared_base(
    tmp_path: Path,
) -> None:
    base = " ".join(
        format_prompt(fragment("base", "OPERATING RULES").node, variables={}).split()
    )
    memory = _memory(tmp_path)
    rendered = " ".join(" ".join(_prompt_texts(memory, explore=False).values()).split())
    for removed, replacements in SHARED_RULE_COVERAGE:
        assert removed not in rendered
        for phrase in replacements:
            assert phrase in base, (removed, phrase)


def test_deduplicated_prompts_keep_the_behavior_of_removed_lines(
    tmp_path: Path,
) -> None:
    """Each rule removed by prompt deduplication is still stated somewhere.

    The migration deleted per-robot duplicates rather than behavior. This table
    records the rules whose wording was removed or shortened, the run modes
    that must still carry them, and asserts the replacement text in the
    rendered prompt.
    """
    memory = _memory(tmp_path)
    rendered = {
        (robot, mode): " ".join(
            _render(robot, explore=mode == "explore", memory=memory).split()
        )
        for robot, _, modes in REMOVED_RULE_COVERAGE
        for mode in modes
    }
    for robot, phrase, modes in REMOVED_RULE_COVERAGE:
        for mode in modes:
            assert phrase in rendered[(robot, mode)], (robot, mode, phrase)


def test_real_robot_rule_is_delivered_once_from_the_shared_mode_fragment(
    tmp_path: Path,
) -> None:
    """Both real-robot slices read the runner-ownership rule from one place."""
    memory = _memory(tmp_path)
    for robot in ("franka", "dual_franka"):
        text = _render(robot, explore=False, memory=memory)
        assert text.count("The runner owns the robot and model processes.") == 1, robot


def test_deduplicated_prompts_keep_the_shared_operating_rules(
    tmp_path: Path,
) -> None:
    for robot, text in _prompt_texts(_memory(tmp_path), explore=False).items():
        normalized = " ".join(text.split())
        assert "read each result before deciding again" in normalized, robot
        assert "Change one thing at a time" in normalized, robot
        assert "Observe before acting" in normalized, robot


def _prompt_source_lines(robot: str) -> int:
    directory = ROOT / "robots" / robot / "prompts"
    files = [path for path in directory.glob("*.py") if path.name != "__init__.py"]
    bundle = ROOT / "robots" / robot / "prompt_bundle.py"
    if bundle.is_file():
        files.append(bundle)
    return sum(
        1
        for path in files
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def rendered_line_count(text: str) -> int:
    """Count the lines of rendered prompt text, including blank separators."""
    stripped = text.rstrip("\n")
    return stripped.count("\n") + 1 if stripped.strip() else 0


def _rendered_lines(node: object, variables: dict[str, object]) -> int:
    """Count the lines a prompt node contributes after rendering."""
    return rendered_line_count(format_prompt(node, variables=variables))


def _section_nodes(contribution: object) -> tuple[object, ...]:
    """Return the prompt nodes of a factory result."""
    if isinstance(contribution, Mapping):
        return tuple(contribution.values())
    return tuple(section.node for section in contribution)


def _slice_variables(
    robot: str,
    memory: Path,
    *,
    explore: bool,
) -> dict[str, object]:
    """Return the variables that fully render one slice's prompt."""
    variables: dict[str, object] = {
        **PROMPT_VARIABLES[robot],
        "mode": "explore" if explore else "eval",
        "memory_dir": str(memory),
        "memory_inbox": str(memory / "_internal/inbox/cell"),
        "session_number": 1,
        "session_max": 1,
        "explore_attempts_per_session": 2,
        "output_dir": "/output",
    }
    variables.setdefault("recipe_tag", f"{robot}_cell")
    return variables


def _rendered_slice_text(
    robot: str,
    memory: Path,
    *,
    explore: bool = False,
) -> dict[str, int]:
    """Render one slice's model-facing text and count it by layer.

    Args:
        robot: Registry name.
        memory: Existing memory corpus, so memory-aware factories render fully.
        explore: Render the exploration workflow instead of the evaluation one.

    Returns:
        Rendered line counts for ``domain``, ``tools``, and ``user``.
    """
    bundle = get_robot_spec(robot).prompts
    variables = _slice_variables(robot, memory, explore=explore)
    tools = (
        _section_nodes(bundle.tool_sections(variables))
        if bundle.tool_sections is not None
        else ()
    )
    return {
        "domain": sum(
            _rendered_lines(node, variables)
            for node in _section_nodes(bundle.system(variables))
        ),
        "tools": sum(_rendered_lines(node, variables) for node in tools),
        "user": sum(
            _rendered_lines(node, variables)
            for node in _section_nodes(bundle.user(variables))
        ),
    }


def _rendered_slice_totals(memory: Path) -> dict[str, int]:
    """Return each slice's rendered domain, tool, and user line total."""
    return {
        robot: sum(_rendered_slice_text(robot, memory).values())
        for robot in PROMPT_VARIABLES
    }


def test_rendered_slice_prompt_meets_domain_targets_and_stays_within_budget(
    tmp_path: Path,
) -> None:
    """Bound what the model reads rather than the Python that renders it.

    The domain layer must meet its acceptance for every slice. Per-slice
    ceilings carry a small trade headroom; the aggregate stays at the measured
    total, so the suite cannot grow overall. The follow-up rendered total is
    lower because shared tool guidance has not yet replaced the slice tool
    text.
    """
    memory = tmp_path / "memory"
    (memory / "global").mkdir(parents=True)
    (memory / "global" / "GLOBAL_MEMORY.md").write_text("# Global memory\n")

    totals = {}
    for robot in PROMPT_VARIABLES:
        layers = _rendered_slice_text(robot, memory)
        target = PROMPT_DOMAIN_RENDERED_TARGET.get(
            robot, PROMPT_DOMAIN_RENDERED_TARGET["other"]
        )
        assert layers["domain"] <= target, (robot, layers)
        totals[robot] = sum(layers.values())
        assert totals[robot] <= PROMPT_SLICE_RENDERED_BUDGET[robot], (
            robot,
            layers,
        )
    assert sum(totals.values()) <= PROMPT_SLICE_RENDERED_TOTAL_BUDGET, totals


def test_explore_budget_covers_every_slice_that_reaches_exploration() -> None:
    """Every slice that can run exploration must record its own ceiling.

    The budget test below iterates the mapping, so a robot missing from it
    would skip the check silently. Deriving the expected keys from the robot
    specs keeps ``franka``, which does not support exploration, out of the
    mapping while making a new exploration-capable slice fail until it has a
    measured ceiling.
    """
    exploration = {
        robot
        for robot in PROMPT_VARIABLES
        if get_robot_spec(robot).supports_exploration
    }

    assert set(PROMPT_EXPLORE_SLICE_RENDERED_BUDGET) == exploration


def test_rendered_explore_slice_prompt_stays_within_budget(tmp_path: Path) -> None:
    """The evaluation ceilings do not cover a slice's exploration workflow.

    Every slice that supports exploration renders a longer domain and tool
    layer in exploration mode, so each one needs its own ceiling. Per-slice
    ceilings carry 5% headroom; the aggregate stays at the measured total.
    """
    memory = _memory(tmp_path)
    totals = {}
    for robot, target in PROMPT_EXPLORE_SLICE_RENDERED_BUDGET.items():
        layers = _rendered_slice_text(robot, memory, explore=True)
        totals[robot] = sum(layers.values())
        assert totals[robot] <= target, (robot, layers)
    assert sum(totals.values()) <= PROMPT_EXPLORE_SLICE_RENDERED_TOTAL_BUDGET, totals


@pytest.mark.xfail(
    strict=True,
    reason=(
        "shared tool guidance must replace the slice tool text before the "
        "follow-up rendered total is reachable"
    ),
)
def test_rendered_slice_prompt_reaches_the_follow_up_total(tmp_path: Path) -> None:
    """Track the rendered total that shared tool guidance will make reachable."""
    memory = tmp_path / "memory"
    (memory / "global").mkdir(parents=True)
    (memory / "global" / "GLOBAL_MEMORY.md").write_text("# Global memory\n")

    totals = _rendered_slice_totals(memory)
    assert sum(totals.values()) <= PROMPT_SLICE_RENDERED_TOTAL_TARGET, totals


#: A copied paragraph is only meaningful above this many characters; shorter
#: lines repeat legitimately as tool names, section labels, and task keys.
COPIED_PARAGRAPH_THRESHOLD = 60


def _named_contributions(
    contribution: object,
) -> tuple[tuple[str, object], ...]:
    """Return the named nodes of one bundle contribution."""
    if contribution is None:
        return ()
    if isinstance(contribution, Mapping):
        return tuple((str(name), body) for name, body in contribution.items())
    if isinstance(contribution, PromptSection):
        return ((contribution.name, contribution.node),)
    return tuple((section.name, section.node) for section in contribution)


def _slice_owned_nodes(
    robot: str,
    memory: Path,
    *,
    explore: bool,
) -> list[tuple[str, str]]:
    """Return the rendered prompt sections this slice's own files contribute."""
    bundle = get_robot_spec(robot).prompts
    variables = _slice_variables(robot, memory, explore=explore)
    tools = bundle.tool_sections(variables) if bundle.tool_sections else None
    return [
        (name, format_prompt(node, variables=variables))
        for contribution in (bundle.system(variables), tools, bundle.user(variables))
        for name, node in _named_contributions(contribution)
    ]


#: Characters :class:`~rpent.prompt.utils.format_prompt` uses for section
#: rules and list markers. They do not carry prompt content.
_RULE_CHARACTERS = frozenset("═─=#*|+ \t")


def _paragraphs(text: str) -> set[str]:
    """Return the normalized paragraphs that carry distinctive prompt content.

    A rendered section title repeats a short label (``BEGIN``) inside a rule of
    ``═`` characters. That line is formatting, not a copied rule, so the
    threshold applies to the paragraph without its rule characters.
    """
    paragraphs = set()
    for part in re.split(r"\n\s*\n", text):
        normalized = " ".join(part.split())
        content = "".join(
            character for character in normalized if character not in _RULE_CHARACTERS
        )
        if len(content) >= COPIED_PARAGRAPH_THRESHOLD:
            paragraphs.add(normalized)
    return paragraphs


def _fragment_paragraphs() -> set[str]:
    """Return every paragraph the shared fragments already state once."""
    return {
        paragraph
        for path in (ROOT / "rpent/prompt/fragments").glob("*.md")
        for paragraph in _paragraphs(path.read_text(encoding="utf-8"))
    }


def test_slice_owned_prompt_paragraphs_are_not_copied(tmp_path: Path) -> None:
    """A slice must not restate a paragraph another slice or a fragment owns.

    The shared fragments are the one place a common rule lives. A slice that
    copies one of their paragraphs creates the second source the layer order
    exists to remove, and the same paragraph in two slices means one of them
    wrote what a fragment should own.
    """
    memory = _memory(tmp_path)
    shared = _fragment_paragraphs()
    owners: dict[str, set[str]] = {}
    copied: list[tuple[str, str]] = []
    for robot in PROMPT_VARIABLES:
        for explore in (False, True):
            mode = "explore" if explore else "eval"
            for name, text in _slice_owned_nodes(robot, memory, explore=explore):
                for paragraph in _paragraphs(text):
                    owners.setdefault(paragraph, set()).add(robot)
                    if paragraph in shared:
                        copied.append((f"{robot}:{mode}/{name}", paragraph[:80]))

    duplicated = {
        tuple(sorted(robots)): paragraph[:80]
        for paragraph, robots in owners.items()
        if len(robots) >= 2
    }
    assert not copied, copied
    assert not duplicated, duplicated


def test_prompt_source_lines_do_not_grow() -> None:
    """Keep prompt sources from growing between intended reductions.

    The measured model-facing bound is
    :func:`test_rendered_slice_prompt_meets_domain_targets_and_stays_within_budget`.
    This ratchet covers the Python around it, so a new mapping or helper cannot
    quietly re-grow the slice files. A slice may use its 5% headroom only by
    consuming another slice's reduction; the aggregate stays at the measured
    total. Lower both after a deliberate prompt change; never raise the
    aggregate without one.
    """
    counts = {robot: _prompt_source_lines(robot) for robot in PROMPT_VARIABLES}
    total = sum(counts.values())

    assert all(
        count <= PROMPT_SLICE_LINE_BUDGET[robot] for robot, count in counts.items()
    ), counts
    assert total <= PROMPT_SOURCE_LINE_BUDGET, counts


@pytest.mark.xfail(
    strict=True,
    reason=(
        "slice-owned prompt source is still above the 1,200-line design "
        "target; the shared tool guidance a_3 adds removes the rest"
    ),
)
def test_prompt_source_lines_reach_the_design_target() -> None:
    """Track the design target after the shared tool guidance lands."""
    counts = {robot: _prompt_source_lines(robot) for robot in PROMPT_VARIABLES}
    assert sum(counts.values()) <= PROMPT_SOURCE_LINE_TARGET, counts
