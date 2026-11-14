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

from rpent.prompt.utils import BulletList, Numbered

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


@pytest.mark.parametrize(
    ("module", "case", "build"),
    BUNDLES,
    ids=[case for _, case, _ in BUNDLES],
)
def test_system_prompt_explains_call_and_execution_layers(
    module, case, build, tmp_path
) -> None:
    prompt = importlib.import_module(module).system_prompt(build(tmp_path))

    assert isinstance(prompt, dict)
    section = prompt["TOOL RESULTS"]
    assert "call_ok" in section
    assert "execution_status" in section
    assert "no_execution" in section
    assert "execution_uncertain" in section
    assert "never" in section and "succeeded" in section

    motion_fields = ("stop_reason", "stop_evidence", "pose_error")
    if case.startswith("robotwin"):
        assert all(field in section for field in motion_fields)
    else:
        assert not any(field in section for field in motion_fields)


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
    prompt = importlib.import_module(module).system_prompt(build(tmp_path))

    text = _prompt_text(prompt)
    assert text
    reasons = _stop_reason_values(REPO_ROOT / producer)
    assert reasons
    undocumented = sorted(reason for reason in reasons if reason not in text)
    assert not undocumented, f"{case} does not explain {undocumented}"
