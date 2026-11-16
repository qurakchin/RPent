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

"""Every robot prompt explains the shared tool-result layers."""

from __future__ import annotations

import ast
import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from rpent.prompt.assembly import build_robot_prompt, fragment, run_axes
from rpent.prompt.utils import BulletList, Numbered
from rpent.robots import get_robot_spec
from tests.unit_tests.rpent.robots.test_registry_contracts import PROMPT_VARIABLES

REPO_ROOT = Path(__file__).resolve().parents[3]


def _plain(**variables):
    return lambda _tmp_path: variables


def _robocasa(mode):
    # The RoboCasa evaluation prompt resolves its memory layers while the
    # prompt is built, so the bundle needs a corpus root and task name.
    def build(tmp_path):
        root = tmp_path / "memory"
        (root / "global").mkdir(parents=True)
        (root / "global" / "GLOBAL_MEMORY.md").write_text("# Global memory\n")
        return {
            "mode": mode,
            "memory_dir": str(root),
            "task_name": "OpenDrawer",
            "split": "target",
        }

    return build


BUNDLES = [
    ("robots.franka.prompt_bundle", "franka", _plain()),
    ("robots.yam.prompt_bundle", "yam", _plain()),
    ("robots.libero.prompt_bundle", "libero-eval", _plain(mode="eval")),
    ("robots.libero.prompt_bundle", "libero-explore", _plain(mode="explore")),
    ("robots.robocasa.prompt_bundle", "robocasa-eval", _robocasa("eval")),
    ("robots.robocasa.prompt_bundle", "robocasa-explore", _robocasa("explore")),
    ("robots.robodojo.prompt_bundle", "robodojo-eval", _plain(mode="eval")),
    ("robots.robodojo.prompt_bundle", "robodojo-explore", _plain(mode="explore")),
    ("robots.dual_franka.prompt_bundle", "dual-franka-eval", _plain(mode="eval")),
    ("robots.dual_franka.prompt_bundle", "dual-franka-explore", _plain(mode="explore")),
    (
        "robots.robotwin.prompt_bundle",
        "robotwin-eval",
        _plain(mode="eval", policy_kind="vla"),
    ),
    (
        "robots.robotwin.prompt_bundle",
        "robotwin-explore",
        _plain(mode="explore", policy_kind="vla"),
    ),
]


def test_shared_tool_result_contract_explains_both_layers() -> None:
    text = _prompt_text(fragment("tool_results", "TOOL RESULTS").node)

    assert "call_ok" in text
    assert "execution_status" in text
    assert "no_execution" in text
    assert "execution_uncertain" in text
    assert "never" in text and "succeeded" in text
    # Motion stop fields belong to the hosts that register MotionTools, not to
    # the shared contract every robot receives.
    assert "stop_evidence" not in text
    assert "pose_error" not in text


@pytest.mark.parametrize("robot_name", sorted(PROMPT_VARIABLES))
def test_assembly_gives_every_robot_the_shared_tool_result_section(
    robot_name, tmp_path
) -> None:
    memory = tmp_path / "memory"
    (memory / "global").mkdir(parents=True)
    (memory / "global" / "GLOBAL_MEMORY.md").write_text("# Global memory\n")
    spec = get_robot_spec(robot_name)
    variables = {
        **PROMPT_VARIABLES[robot_name],
        "mode": "eval",
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
        axes=run_axes(explore=False, dashboard=False, real_robot=spec.is_real_robot),
    )

    names = [section["name"] for section in assembled.sections]
    assert "TOOL RESULTS" in names
    # Tool guidance is its own layer, ahead of the robot's domain sections.
    assert names.index("TOOL RESULTS") < names.index("MEMORY — HOW TO READ")
    assert "call_ok" in assembled.system


@pytest.mark.parametrize(
    ("module", "case", "build"),
    BUNDLES,
    ids=[case for _, case, _ in BUNDLES],
)
def test_motion_result_fields_are_documented_only_where_motion_tools_exist(
    module, case, build, tmp_path
) -> None:
    bundle = importlib.import_module(module)
    variables = build(tmp_path)
    text = _sections_text(bundle.tool_sections(variables))
    text += _sections_text(bundle.system_prompt(variables))

    motion_fields = ("stop_evidence", "pose_error")
    if case.startswith("robotwin"):
        assert all(field in text for field in motion_fields)
    else:
        assert not any(field in text for field in motion_fields)


# Hosts whose tools report ``stop_reason`` and the module that decides the value.
# The planner can only act on a reason it was told about, so each producer's
# vocabulary must appear in its host prompt.
STOP_REASON_PRODUCERS = {
    "robotwin-eval": "rpent/tools/motion_tools.py",
    "robotwin-explore": "rpent/tools/motion_tools.py",
    "robodojo-eval": "robots/robodojo/primitives.py",
    "robodojo-explore": "robots/robodojo/primitives.py",
}
BUNDLES_BY_CASE = {case: (module, build) for module, case, build in BUNDLES}


def _prompt_text(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, Mapping):
        return "\n".join(_prompt_text(value) for value in node.values())
    if isinstance(node, (BulletList, Numbered)):
        return "\n".join(_prompt_text(item) for item in node.items)
    if isinstance(node, Sequence):
        return "\n".join(_prompt_text(item) for item in node)
    return ""


def _sections_text(sections) -> str:
    return "\n".join(_prompt_text(section.node) for section in sections)


def _stop_reason_values(path: Path) -> set[str]:
    """Collect literal stop reasons a module can report, without running it."""
    tree = ast.parse(path.read_text())

    def literals(node: ast.AST) -> set[str]:
        """Read literal branches of a reason expression, not its inputs."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value} if node.value.isidentifier() else set()
        if isinstance(node, (ast.Tuple, ast.List, ast.BoolOp)):
            values: set[str] = set()
            for child in node.elts if hasattr(node, "elts") else node.values:
                values |= literals(child)
            return values
        if isinstance(node, ast.IfExp):
            return literals(node.body) | literals(node.orelse)
        return set()

    reasons: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = {
                name.id
                for target in node.targets
                for name in ast.walk(target)
                if isinstance(name, ast.Name)
            }
            if targets & {"reason", "stop_reason"}:
                reasons |= literals(node.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "stop_reason":
                    reasons |= literals(value)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in {"stop_reason", "stop_reason_override"}:
                    reasons |= literals(keyword.value)
        elif isinstance(node, ast.FunctionDef) and node.name == "stop_reason":
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    reasons |= literals(child.value)
    return reasons


@pytest.mark.parametrize(
    ("case", "producer"),
    sorted(STOP_REASON_PRODUCERS.items()),
    ids=sorted(STOP_REASON_PRODUCERS),
)
def test_prompt_documents_each_stop_reason_its_tools_emit(
    case, producer, tmp_path
) -> None:
    module, build = BUNDLES_BY_CASE[case]
    bundle = importlib.import_module(module)
    variables = build(tmp_path)

    text = _sections_text(bundle.system_prompt(variables))
    text += "\n" + _sections_text(bundle.tool_sections(variables))
    assert text
    reasons = _stop_reason_values(REPO_ROOT / producer)
    assert reasons
    undocumented = sorted(reason for reason in reasons if reason not in text)
    assert not undocumented, f"{case} does not explain {undocumented}"


#: Modules that own a planner-driven move_to. A plan the planner refuses is one
#: event, so every slice names it the same way and reports the same layer.
PLANNER_MOTION_PRODUCERS = (
    "rpent/tools/motion_tools.py",
    "robots/robodojo/primitives.py",
    "robots/yam/primitives.py",
)


@pytest.mark.parametrize("producer", PLANNER_MOTION_PRODUCERS)
def test_planner_slices_share_one_plan_rejection_reason(producer) -> None:
    reasons = _stop_reason_values(REPO_ROOT / producer)

    assert "planning_rejected" in reasons
    assert "plan_failed" not in reasons
