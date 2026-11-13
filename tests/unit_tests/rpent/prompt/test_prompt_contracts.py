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
- no prompt asks for ``corroborations.jsonl`` or ``conflict_<id>.md``, which
  the merge step does not consume;
- proposals use a bare ``id`` in both scopes;
- a deleted per-robot reminder stays covered by a shared or robot-local rule.
  For example, the dual-Franka VLA segment stop is covered by
  ``VLA SEGMENT GATES`` and the single-attempt rules by ``base.md``.
"""

from __future__ import annotations

from pathlib import Path

from rpent.prompt.assembly import build_robot_prompt, run_modes
from rpent.robots import get_robot_spec
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

ROOT = Path(__file__).resolve().parents[4]
PROMPT_LINE_BUDGET = 2360


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


REMOVED_RULE_COVERAGE = (
    (
        "franka",
        "If state, cameras, or motion results disagree, stop instead of guessing.",
    ),
    (
        "franka",
        "Inspect view_env_state before motion and after every mutating tool call.",
    ),
    (
        "dual_franka",
        "configured inline camera view(s) as the primary visual source of truth",
    ),
    (
        "dual_franka",
        "These boundaries only mean a segment ended; verify physical success",
    ),
)


def test_deduplicated_prompts_keep_the_behavior_of_removed_lines(
    tmp_path: Path,
) -> None:
    """Each rule removed by prompt deduplication is still stated somewhere.

    The migration deleted per-robot duplicates rather than behavior. This table
    records the rules whose wording was removed or shortened and asserts the
    replacement text in the robot-local prompt.
    """
    memory = _memory(tmp_path)
    rendered = {
        robot: " ".join(_render(robot, explore=False, memory=memory).split())
        for robot, _ in REMOVED_RULE_COVERAGE
    }
    for robot, phrase in REMOVED_RULE_COVERAGE:
        assert phrase in rendered[robot], (robot, phrase)


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
