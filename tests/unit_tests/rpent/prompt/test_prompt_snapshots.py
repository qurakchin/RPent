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

"""Snapshot the assembled prompt for every reachable robot and run mode.

The fixture records the ordered section names, the prompt digest, and the
rendered line count for the fixed variables in ``PROMPT_VARIABLES``. Variants
come from the robot spec: evaluation always, exploration only when
``supports_exploration`` is set, and Dashboard whenever ``resolve_dashboard``
is available. A mismatch means a prompt change was not intended or the fixture
was not refreshed; update ``prompt_snapshot.json`` deliberately with the same
variables when the change is intended.
"""

from __future__ import annotations

import json
from pathlib import Path

from rpent.prompt.assembly import build_robot_prompt, prompt_sha256, run_axes
from rpent.robots import get_robot_spec
from tests.unit_tests.rpent.prompt.test_prompt_contracts import rendered_line_count
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

SNAPSHOT = Path(__file__).with_name("prompt_snapshot.json")
#: No-growth ceiling for every reachable evaluation and exploration prompt
#: combined, in rendered lines. Dashboard prompts are recorded in the fixture
#: but not counted here because they are assembled per claimed task. The
#: earlier 14-combo baseline included the unreachable ``franka:explore``
#: variant; the spec-derived set excludes it.
PROMPT_FULL_RENDERED_BUDGET = 5050


def _memory_dir(tmp_path: Path) -> Path:
    """Create the minimal memory corpus the prompt factories expect."""
    memory = tmp_path / "memory"
    (memory / "global").mkdir(parents=True)
    (memory / "global/GLOBAL_MEMORY.md").write_text(
        "# Global memory\n", encoding="utf-8"
    )
    return memory


def _normalize(text: str, memory: Path) -> str:
    """Replace the temporary corpus path so the digest is machine-independent."""
    return text.replace(str(memory.resolve()), "<memory>").replace(
        str(memory), "<memory>"
    )


def _variants(spec: object) -> tuple[tuple[str, bool, bool], ...]:
    """Return the run-mode variants the robot spec can actually reach."""
    variants = [("eval", False, False)]
    if getattr(spec, "supports_exploration", False):
        variants.append(("explore", True, False))
    if getattr(spec, "resolve_dashboard", None) is not None:
        variants.append(("dashboard", False, True))
    return tuple(variants)


def _rendered_snapshot(memory: Path) -> dict[str, dict[str, object]]:
    actual: dict[str, dict[str, object]] = {}
    for robot_name, base in PROMPT_VARIABLES.items():
        spec = get_robot_spec(robot_name)
        for label, explore, dashboard in _variants(spec):
            variables = {
                **base,
                "mode": "explore" if explore else "eval",
                "memory_dir": str(memory),
                "memory_inbox": str(memory / "_internal/inbox/cell"),
                "session_number": 1,
                "session_max": 1,
                "explore_attempts_per_session": 2,
                "output_dir": "/output",
            }
            variables.setdefault("recipe_tag", f"{robot_name}_cell")
            assembled = build_robot_prompt(
                spec.prompts,
                robot_name=robot_name,
                variables=variables,
                axes=run_axes(
                    explore=explore,
                    dashboard=dashboard,
                    real_robot=spec.is_real_robot,
                ),
            )
            system = _normalize(assembled.system, memory)
            user = _normalize(assembled.user, memory)
            key = f"{robot_name}:{label}"
            actual[key] = {
                "sections": [section["name"] for section in assembled.sections],
                "prompt_sha256": prompt_sha256(system, user),
                "rendered_lines": (
                    rendered_line_count(system) + rendered_line_count(user)
                ),
            }
    return actual


def test_assembled_prompts_match_the_recorded_snapshot(tmp_path: Path) -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = _rendered_snapshot(_memory_dir(tmp_path))

    assert set(actual) == set(expected)
    for key in expected:
        assert actual[key]["sections"] == expected[key]["sections"], key
        assert actual[key]["prompt_sha256"] == expected[key]["prompt_sha256"], key
        assert actual[key]["rendered_lines"] == expected[key]["rendered_lines"], key

    total = sum(
        expected[key]["rendered_lines"]
        for key in expected
        if key.endswith((":eval", ":explore"))
    )
    assert total <= PROMPT_FULL_RENDERED_BUDGET, total
