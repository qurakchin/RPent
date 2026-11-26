# Copyright 2026 The RPent Authors.
"""Public CLI chain with a local model planner and real RoboDojo runtime."""

import json
import os
from contextlib import closing
from pathlib import Path

import pytest

from robots.robodojo.robot_spec import get_robot_spec
from robots.robodojo.toolkit import RoboDojoToolkit
from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.planner.api_loop import ApiAgentLoop
from rpent.planner.base import build_api_model
from rpent.session.planner_capture import end_planner_task, start_planner_task
from tests.e2e_tests.common import (
    PLANNER_MODEL,
    PLANNER_TIMEOUT_SECONDS,
    ToolExample,
    parse_runtime_args,
    planner_url,
    publish_check,
    require_model_path,
    run_policy_chain,
    runtime_phase,
)
from tests.e2e_tests.guided_planner_proxy import TOOL_TEST_ROLE, GuidedPlannerProxy
from tests.e2e_tests.tool_coverage import inspect_trajectory

pytestmark = [
    pytest.mark.timeout(2400),
    pytest.mark.skipif(
        os.environ.get("RPENT_RUN_ROBODOJO_INTEGRATION") != "1",
        reason="requires a reserved GPU, RoboDojo assets and model checkpoints",
    ),
]


def test_simulator_tool_coverage(robodojo_runtime_argv, monkeypatch):
    """Exercise the simulator and SAM3 toolkit independently of policy weights."""
    from rpent.utils import logging

    require_model_path("SAM3_CHECKPOINT_PATH", file=True)
    output = Path(os.environ["RPENT_E2E_OUTPUT_DIR"]) / "simulator-tools"
    monkeypatch.setattr(logging, "_output_dir", output)
    monkeypatch.setenv("OPENAI_API_KEY", "local")
    spec = get_robot_spec()
    args = parse_runtime_args(
        spec,
        [
            "--task",
            "put_bottles_into_dustbin",
            "--seed",
            "0",
            "--layout",
            "0",
            *robodojo_runtime_argv,
        ],
    )
    with runtime_phase(spec, args, output, {"env", "sam3"}) as runtime:
        events = NullDashboardEventSink()
        with closing(
            RoboDojoToolkit(
                primitives_kwargs=runtime,
                dashboard_events=events,
                memory=MemoryManager(output / "memory"),
                state_output_dir=output,
            )
        ) as toolkit:
            prompt = "Exercise each available tool once."
            with GuidedPlannerProxy(
                planner_url(),
                output_dir=output,
                examples={"set_gripper": {"arm": "left", "val": 0.5, "steps": 2}},
                role_prompt=TOOL_TEST_ROLE,
                timeout_s=PLANNER_TIMEOUT_SECONDS,
            ) as proxy:
                planner = ApiAgentLoop(
                    model=build_api_model(f"vllm:{PLANNER_MODEL}", proxy.base_url),
                    dashboard_events=events,
                    max_tokens=512,
                    timeout_s=PLANNER_TIMEOUT_SECONDS,
                )
                start_planner_task(
                    toolkit.state,
                    instruction=prompt,
                    config={"seed": 0, "model": PLANNER_MODEL},
                )
                result = planner.solve(
                    system_prompt=TOOL_TEST_ROLE,
                    user_message=prompt,
                    toolkit=toolkit,
                    max_turns=64,
                )
                end_planner_task(
                    toolkit.state,
                    result,
                    finish_result=result.finish_result,
                    environment_success=None,
                    exception=None,
                )
            report = inspect_trajectory(output, "set_gripper")
            assert report["passed"], report
            assert result.error is None and result.finish_result, result.error


@pytest.mark.parametrize("control", ["primitive", "policy"])
@pytest.mark.parametrize("vla_backend", ["vpp2", "awomo05"])
def test_policy_chain(control, vla_backend, robodojo_model_argv):
    require_model_path("SAM3_CHECKPOINT_PATH", file=True)
    if control == "primitive":
        action = ToolExample("set_gripper", {"arm": "left", "val": 0.5, "steps": 2})
    else:
        arguments = {"chunks": 1}
        if vla_backend == "vpp2":
            arguments["instruction"] = "Pick up the pink bottle on the table"
        action = ToolExample(f"{vla_backend}_act", arguments)
    output = Path(os.environ["RPENT_E2E_OUTPUT_DIR"]) / (
        f"policy-chain-{action.name}"
        if vla_backend == "vpp2"
        else f"policy-chain-awomo05-{action.name}"
    )
    result = run_policy_chain(
        robot="robodojo",
        robot_argv=[
            "--task",
            "put_bottles_into_dustbin",
            "--seed",
            "0",
            "--layout",
            "0",
            *robodojo_model_argv(vla_backend),
        ],
        output_dir=output,
        action=action,
        action_count_field="executed_actions",
        before_action_calls=(
            ToolExample("view_env_state", {"step": 0}),
            ToolExample(
                "segment", {"text_prompt": "the pink bottle on the table", "step": 0}
            ),
            ToolExample(
                "sample_world_xyz", {"view": "head", "pixels": [[240, 320]], "step": 0}
            ),
        ),
        require_post_action_image=True,
    )
    assert result["post_action_new_image_count"] > 0, result
    transcript = json.loads((output / result["transcript"]).read_text(encoding="utf-8"))
    assert transcript["error"] is None, transcript["error"]
    reads = {
        message["name"]: json.loads(message["content"])
        for message in transcript["messages"]
        if message.get("role") == "tool"
        and message.get("name") in {"view_env_state", "segment", "sample_world_xyz"}
    }
    assert set(reads) == {"view_env_state", "segment", "sample_world_xyz"}
    assert all(not payload.get("error") for payload in reads.values()), reads
    assert reads["sample_world_xyz"]["samples"][0]["valid_points"] > 0, reads
    segments = list(output.glob("segment_*.json/00.json"))
    assert len(segments) == 1, segments
    segment = json.loads(segments[0].read_text(encoding="utf-8"))
    assert segment["found"] and segment["score"] >= 0.2, segment
    assert segment["step_idx"] == 0 and segment["camera"] == "cam_head"
    result["definition"] = (
        f"local model planner -> public CLI -> toolkit -> {action.name} -> finish"
    )
    publish_check(f"robodojo_{action.name}_policy_chain", result)
