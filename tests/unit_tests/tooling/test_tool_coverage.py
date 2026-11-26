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
