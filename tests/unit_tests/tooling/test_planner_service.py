# Copyright 2026 The RPent Authors.
"""Planner wrappers preserve test status and stop only owned services."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[2] / "e2e_tests/with_planner.sh"


@pytest.mark.parametrize(
    ("test_status", "startup_failure"), [(0, False), (7, False), (0, True)]
)
def test_owned_service_stops_after_tests(tmp_path, test_status, startup_failure):
    root = tmp_path / "planner"
    venv = root / "venv"
    model = root / "model"
    binary = venv / "bin/vllm"
    binary.parent.mkdir(parents=True)
    model.mkdir(parents=True)
    pid_file = root / "pid"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import http.server, os, pathlib, sys\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        f"if {startup_failure!r}: raise SystemExit(3)\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "class Handler(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        "http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()\n"
    )
    binary.chmod(0o755)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    env.pop("RPENT_E2E_PLANNER_URL", None)
    env.update(
        RPENT_E2E_PLANNER_VENV=str(venv),
        RPENT_E2E_PLANNER_MODEL=str(model),
        RPENT_E2E_PLANNER_CACHE=str(root / "cache"),
        RPENT_E2E_PLANNER_PORT=str(port),
    )
    result = subprocess.run(
        [
            "bash",
            str(WRAPPER),
            str(tmp_path / "server.log"),
            sys.executable,
            "-c",
            f"raise SystemExit({test_status})",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == (1 if startup_failure else test_status), result.stderr
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_external_service_is_borrowed(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/v1/models" else 404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                "bash",
                str(WRAPPER),
                str(tmp_path / "unused.log"),
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ],
            env={
                **os.environ,
                "RPENT_E2E_PLANNER_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "RPENT_E2E_PLANNER_VENV": str(tmp_path / "must-not-exist"),
                "RPENT_E2E_PLANNER_MODEL": str(tmp_path / "must-not-exist-model"),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 7, result.stderr
        assert thread.is_alive()
        assert not (tmp_path / "must-not-install").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
