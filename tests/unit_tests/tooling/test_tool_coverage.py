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


def test_each_requested_schema_advances_even_if_model_misses_a_call(tmp_path):
    from tests.e2e_tests.guided_planner_proxy import GuidedPlannerProxy

    proxy = GuidedPlannerProxy(
        "http://127.0.0.1:1/v1",
        output_dir=tmp_path,
        examples={"act": {"chunks": 1}},
    )
    request = {
        "model": "Qwen3.5-0.8B",
        "messages": [
            {"role": "system", "content": "Original robot prompt"},
            {"role": "user", "content": "Solve the task."},
        ],
        "tools": [
            {"type": "function", "function": {"name": "act", "parameters": {}}},
            {"type": "function", "function": {"name": "list_dir", "parameters": {}}},
            {"type": "function", "function": {"name": "finish", "parameters": {}}},
        ],
    }
    for name in ("list_dir", "act", "finish"):
        step = proxy.rewrite_request(request)
        assert [tool["function"]["name"] for tool in step["tools"]] == [name]
        assert step["parallel_tool_calls"] is False
        assert step["tool_choice"] == ("auto" if name == "finish" else "required")
    report = inspect_trajectory(tmp_path, "act")
    assert report["missing"] == ["act", "finish", "list_dir"]
    assert not report["passed"]


def test_guided_proxy_forwards_rewritten_chat_completion(tmp_path):
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from tests.e2e_tests.guided_planner_proxy import GuidedPlannerProxy

    seen: list[dict] = []

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            seen.append(body)
            reply = json.dumps(
                {"choices": [{"message": {"role": "assistant"}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *_args):
            return

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    thread = Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        upstream_url = f"http://127.0.0.1:{upstream.server_port}/v1"
        with GuidedPlannerProxy(
            upstream_url, output_dir=tmp_path, examples={"act": {"chunks": 1}}
        ) as proxy:
            req = urllib.request.Request(
                f"{proxy.base_url}/chat/completions",
                data=json.dumps(
                    {
                        "model": "Qwen3.5-0.8B",
                        "messages": [{"role": "user", "content": "hi"}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {"name": "act", "parameters": {}},
                            },
                            {
                                "type": "function",
                                "function": {"name": "finish", "parameters": {}},
                            },
                        ],
                    }
                ).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=5) as resp:
                assert resp.status == 200
                assert json.loads(resp.read())["choices"]
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)

    assert len(seen) == 1
    assert [t["function"]["name"] for t in seen[0]["tools"]] == ["act"]
    assert '"chunks": 1' in seen[0]["messages"][-1]["content"]
    assert json.loads((tmp_path / "tool-inventory.json").read_text()) == [
        "act",
        "finish",
    ]
