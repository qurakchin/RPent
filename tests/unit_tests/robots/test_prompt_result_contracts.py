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

import importlib

import pytest


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
