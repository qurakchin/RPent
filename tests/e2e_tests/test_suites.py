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

"""Generic pytest entrypoint for declarative GPU E2E suites."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tests.e2e_tests.runner import publish_check, run_case, selected_cuda_ordinal
from tests.e2e_tests.suite import load_suite, resolve_case


def _selected_cases() -> list[Any]:
    suite_name = os.environ.get("RPENT_E2E_SUITE", "").strip()
    if not suite_name:
        return []
    suite = load_suite(suite_name)
    return [
        pytest.param(suite, case, id=f"{suite_name}:{case['name']}")
        for case in suite["cases"]
    ]


@pytest.mark.parametrize(("suite", "case"), _selected_cases())
def test_suite_case(
    suite: dict[str, Any],
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = Path(os.environ.get("RPENT_E2E_OUTPUT_DIR", str(tmp_path)))
    case_output = output_root / case["name"]
    gpu = str(selected_cuda_ordinal())
    resolved = resolve_case(suite, case, output_dir=case_output, gpu=gpu)
    if resolved["missing"]:
        pytest.skip("; ".join(resolved["missing"]))

    for key, value in resolved["env"].items():
        if value.startswith(f"{case_output}/") and not Path(value).suffix:
            Path(value).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(key, value)

    result = run_case(
        robot=resolved["robot"],
        robot_argv=resolved["args"],
        output_dir=case_output,
        action_tool=resolved["action_tool"],
        action_count_field=resolved["action_count_field"],
        tool_args=resolved["tool_args"],
        require_post_action_image=resolved["require_post_action_image"],
    )
    assert result["status"] == "passed"
    publish_check(f"{suite['suite']}_{case['name']}", result)
