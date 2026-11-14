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

from rpent.prompt.assembly import build_robot_prompt, fragment, run_axes
from rpent.prompt.utils import format_prompt
from rpent.robots import get_robot_spec
from rpent.robots.prompt_bundle import PromptBundle
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

ROOT = Path(__file__).resolve().parents[4]
#: Aggregate source ceiling, including the section mappings and formatting that
#: never reach the model. While every slice sits at its measured count the
#: per-slice ceilings below already bound the total; this one binds after a
#: slice is reduced, so the freed ceiling cannot be reused by another slice.
#: The model-facing bound is :data:`PROMPT_SLICE_RENDERED_BUDGET`.
PROMPT_SOURCE_LINE_BUDGET = 2395
#: Design target for slice-owned prompt source (``a_2`` §7): the hand-written
#: slice prompts together, including the code-mode prompts ``a_4`` adds. This
#: branch counts ``robots/<robot>/prompts/*.py`` plus ``prompt_bundle.py``
#: without those prompts, so comparing the smaller set to the target is
#: conservative. The strict xfail below records the gap.
PROMPT_SOURCE_LINE_TARGET = 1200
#: Per-slice source ceiling so one robot cannot absorb another's reduction.
PROMPT_SLICE_LINE_BUDGET = {
    "libero": 845,
    "robodojo": 434,
    "robocasa": 308,
    "dual_franka": 268,
    "robotwin": 265,
    "yam": 203,
    "franka": 72,
}

#: Acceptances that describe what the model reads, in rendered lines: the
#: LIBERO domain is a broad benchmark family, the other slices are narrower.
PROMPT_DOMAIN_RENDERED_TARGET = {"libero": 300, "other": 150}
#: Rendered slice text (domain, tool usage, user message) each robot may ship.
#: These are no-growth ratchets at the current measurements; the shared tool
#: guidance ``a_3`` adds is what removes the remaining slice tool text.
PROMPT_SLICE_RENDERED_BUDGET = {
    "libero": 479,
    "robodojo": 256,
    "robocasa": 178,
    "dual_franka": 100,
    "robotwin": 154,
    "yam": 112,
    "franka": 45,
}
#: Follow-up rendered total once shared tool guidance lands. It is not an
#: ``a_2`` design metric; the design target is the source-line count above. The
#: strict xfail below tracks it.
PROMPT_SLICE_RENDERED_TOTAL_TARGET = 1200
#: Aggregate rendered ceiling, with the same role as
#: :data:`PROMPT_SOURCE_LINE_BUDGET`: it binds once a reduced slice leaves
#: slack in its own ceiling.
PROMPT_SLICE_RENDERED_TOTAL_BUDGET = 1324

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
    """Count the non-blank lines of rendered prompt text."""
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


def _rendered_slice_text(robot: str, memory: Path) -> dict[str, int]:
    """Render one slice's model-facing text and count it by layer.

    Args:
        robot: Registry name.
        memory: Existing memory corpus, so memory-aware factories render fully.

    Returns:
        Rendered line counts for ``domain``, ``tools``, and ``user``.
    """
    bundle = get_robot_spec(robot).prompts
    variables = {**PROMPT_VARIABLES[robot], "memory_dir": str(memory)}
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

    The domain layer must meet its acceptance for every slice. The per-slice
    and total budgets are no-growth ratchets at the current measurements; the
    follow-up rendered total is lower because shared tool guidance has not yet
    replaced the slice tool text.
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


def test_prompt_source_lines_do_not_grow() -> None:
    """Keep prompt sources from growing between intended reductions.

    The measured model-facing bound is
    :func:`test_rendered_slice_prompt_meets_domain_targets_and_stays_within_budget`.
    This ratchet covers the Python around it, so a new mapping or helper cannot
    quietly re-grow the slice files. Each slice has its own ceiling so one
    robot's reduction cannot pay for another's growth. Lower both after a
    deliberate prompt change; never raise them without one.
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
