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

The a_2 migration moved shared rules into ``rpent/prompt/fragments``. These
checks keep the model-facing instructions consistent with the shared sources
and the memory manager:

- the tool layer comes from every robot's ``prompt_sections``;
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
from pathlib import Path

from rpent.prompt.assembly import build_robot_prompt, fragment, run_modes
from rpent.prompt.utils import format_prompt
from rpent.robots import get_robot_spec
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

ROOT = Path(__file__).resolve().parents[4]
PROMPT_LINE_BUDGET = 2425

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
        modes=run_modes(
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


def test_every_robot_contributes_a_tool_layer() -> None:
    for robot in PROMPT_VARIABLES:
        assert get_robot_spec(robot).prompts.prompt_sections is not None, robot


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


def test_deduplicated_prompts_keep_the_shared_operating_rules(
    tmp_path: Path,
) -> None:
    for robot, text in _prompt_texts(_memory(tmp_path), explore=False).items():
        normalized = " ".join(text.split())
        assert "read each result before deciding again" in normalized, robot
        assert "Change one thing at a time" in normalized, robot
        assert "Observe before acting" in normalized, robot


def test_prompt_source_lines_do_not_grow_before_a_3_moves_tool_guidance() -> None:
    """Ratchet the hand-written prompt sources while a_3 owns the remaining move.

    The a_2 target is 1,200 lines. Most remaining lines are per-robot tool usage
    that a_3 will move into the shared tool families; until then this ratchet
    blocks silent growth so the next migration starts from a measured baseline.
    The current count includes the ``sections()`` calls that attribute each
    contribution to its module; set the budget to the measured value after a
    deliberate prompt change.
    """
    total = 0
    for robot in PROMPT_VARIABLES:
        directory = ROOT / "robots" / robot / "prompts"
        files = [path for path in directory.glob("*.py") if path.name != "__init__.py"]
        bundle = ROOT / "robots" / robot / "prompt_bundle.py"
        if bundle.is_file():
            files.append(bundle)
        for path in files:
            total += sum(
                1
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )

    assert total <= PROMPT_LINE_BUDGET
