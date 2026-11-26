# Copyright 2026 The RPent Authors.
"""Deterministic FunctionModel tool traversal and trajectory coverage verdicts."""

import asyncio
import json

import pytest
from pydantic_ai import Agent

from tests.e2e_tests.coverage import inspect_trajectory
from tests.e2e_tests.runner import (
    ToolTraversalPolicy,
    build_tool_walker_model,
)


@pytest.mark.parametrize(
    ("turns", "passed"),
    [
        ([["act"], ["finish"]], True),
        ([["finish"]], False),
        ([["act", "finish"]], False),
        ([["failed"], ["act"], ["finish"]], False),
        ([[], ["act"], ["finish"]], False),
    ],
)
def test_planner_trace_verdict(tmp_path, turns, passed):
    directory = tmp_path / "trajectories/one"
    directory.mkdir(parents=True)
    with (directory / "planners.jsonl").open("w") as stream:
        for calls in turns:
            record = {
                "request": {
                    "data": {
                        "model_request_parameters": {
                            "function_tools": [{"name": "act"}],
                            "output_tools": [{"name": "finish"}],
                        }
                    }
                },
                "status": "completed",
                "tool_calls": [
                    {
                        "name": name,
                        "status": "failed" if name == "failed" else "completed",
                        "origin": "model",
                        "arguments": {"data": {}},
                        "raw_result": {"data": {"data": {"error": "missing file"}}}
                        if name == "failed"
                        else None,
                    }
                    for name in calls
                ],
            }
            stream.write(json.dumps(record) + "\n")
    report = inspect_trajectory(tmp_path, "act")
    assert report["passed"] is passed
    if ["failed"] in turns:
        assert report["calls"][0]["error"] == "missing file"
    assert json.loads((tmp_path / "tool-coverage.json").read_text()) == report


def test_deterministic_function_model_exercises_all_tools_in_stream(tmp_path):
    called: list[tuple[str, dict]] = []
    model = build_tool_walker_model(
        output_dir=tmp_path,
        examples={"act": {"chunks": 1}},
    )
    agent = Agent(model)

    @agent.tool_plain
    def act(chunks: int = 5) -> str:
        called.append(("act", {"chunks": chunks}))
        return "acted"

    @agent.tool_plain
    def list_dir(path: str) -> str:
        called.append(("list_dir", {"path": path}))
        return "listed"

    @agent.tool_plain
    def move_to(xyz: list[float], max_steps: int = 50) -> str:
        called.append(("move_to", {"xyz": xyz, "max_steps": max_steps}))
        return "moved"

    @agent.tool_plain
    def finish(status: str, summary: str) -> str:
        called.append(("finish", {"status": status, "summary": summary}))
        return "done"

    async def _run() -> None:
        async with agent.iter("exercise tools") as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as stream:
                        async for _ in stream:
                            pass
                if any(name == "finish" for name, _ in called):
                    break

    asyncio.run(_run())
    assert [name for name, _ in called] == ["list_dir", "act", "move_to", "finish"]
    assert called[0][1] == {"path": str(tmp_path)}
    assert called[1][1] == {"chunks": 1}
    assert called[2][1] == {"xyz": [0.0, 0.0, 0.2], "max_steps": 1}
    assert json.loads((tmp_path / "tool-inventory.json").read_text()) == [
        "act",
        "finish",
        "list_dir",
        "move_to",
    ]


def test_tool_traversal_policy_returns_none_when_no_tools(tmp_path):
    policy = ToolTraversalPolicy(output_dir=tmp_path)
    assert policy.next_call([]) is None
