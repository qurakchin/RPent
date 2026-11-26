# Copyright 2026 The RPent Authors.
"""The GPU smoke verdict requires actual successful model-origin calls."""

import json

import pytest

from tests.e2e_tests.tool_coverage import inspect_trajectory


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


def test_each_requested_schema_advances_even_if_model_misses_a_call(
    tmp_path, monkeypatch
):
    import asyncio

    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.tools import ToolDefinition

    from tests.e2e_tests import planner_cli

    monkeypatch.setattr(planner_cli, "get_output_dir", lambda: tmp_path)
    capability = planner_cli.ExerciseTools()
    request = ModelRequestContext(
        model=TestModel(),
        messages=[ModelRequest([UserPromptPart("Exercise each tool.")])],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(
            function_tools=[
                ToolDefinition(name="act"),
                ToolDefinition(name="list_dir"),
            ],
            output_tools=[ToolDefinition(name="finish", kind="output")],
        ),
    )
    for name in ("list_dir", "act", "finish"):
        step = asyncio.run(capability.before_model_request(None, request))
        params = step.model_request_parameters
        assert [
            tool.name for tool in [*params.function_tools, *params.output_tools]
        ] == [name]
        assert not params.allow_text_output
    report = inspect_trajectory(tmp_path, "act")
    assert report["missing"] == ["act", "finish", "list_dir"]
    assert not report["passed"]
