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

"""Persist real YAM outcomes through the public runner finalization hook."""

from __future__ import annotations

from pathlib import Path

from rpent.evaluation import RunFinalizationContext, write_json_atomic


def finalize_run(context: RunFinalizationContext) -> Path:
    """Keep planner claims separate from operator-backed environment success."""
    context.output_dir.mkdir(parents=True, exist_ok=True)
    status = (
        "unknown"
        if context.environment_success is None
        else "success"
        if context.environment_success
        else "not_successful"
    )
    return write_json_atomic(
        context.output_dir / "result.json",
        {
            "robot": context.robot_name,
            "task": dict(context.task_desc),
            "environment_success": context.environment_success,
            "status": status,
            "success_source": "environment_eval_success",
            "status_meaning": (
                "False means success is not established; it does not by itself "
                "mean the operator judged a physical attempt to have failed."
            ),
            "planner_finish_request": dict(context.finish_result or {}),
            "agent_error": context.agent_error,
            "elapsed_s": context.elapsed_s,
            "planner": context.planner,
            "model": context.model,
            "stats": dict(context.stats),
        },
    )
