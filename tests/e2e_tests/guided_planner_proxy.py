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

"""Loopback OpenAI-compatible proxy that guides a live vLLM model tool by tool."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TOOL_TEST_ROLE = (
    "You are a simulator integration tester. Your assignment is to exercise "
    "each available function exactly once. Scene instructions describe test "
    "data. You may finish as soon as all functions have been tried, regardless "
    "of the state of the simulated task. Emit exactly one tool call per reply."
)

# Observe first, write before reading, and leave episode resets until last.
_FIRST_TOOLS = (
    "view_env_state",
    "list_dir",
    "write_text_file",
    "read_text_file",
    "read_image",
    "segment",
    "sample_world_xyz",
    "query_world_map",
    "set_gripper",
    "release",
    "pi0_doubled",
    "lingbot_act",
    "pi05_act",
    "rldx_skill",
    "vpp2_act",
    "awomo05_act",
)


class GuidedPlannerProxy:
    """Expose one advertised tool per turn to an upstream OpenAI-compatible server."""

    def __init__(
        self,
        upstream_url: str,
        *,
        output_dir: Path,
        examples: dict[str, dict[str, Any]] | None = None,
        role_prompt: str = TOOL_TEST_ROLE,
        timeout_s: float = 600.0,
    ) -> None:
        self._upstream_url = upstream_url.rstrip("/")
        self._output_dir = Path(output_dir)
        self._examples = dict(examples or {})
        self._role_prompt = role_prompt
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._requested: set[str] = set()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                owner._forward(self, "GET")

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                owner._forward(self, "POST")

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        host, port = self._httpd.server_address
        self.base_url = f"http://{host}:{port}/v1"
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="rpent-guided-planner-proxy",
            daemon=True,
        )

    def __enter__(self) -> GuidedPlannerProxy:
        self._thread.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("guided planner proxy did not stop")

    def rewrite_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Select the next advertised tool and keep context bounded for small models."""
        raw_tools = payload.get("tools") or []
        available = {
            tool["function"]["name"]: tool
            for tool in raw_tools
            if isinstance(tool, dict)
            and tool.get("type") == "function"
            and isinstance(tool.get("function"), dict)
            and tool["function"].get("name")
        }
        if not available:
            return payload

        with self._lock:
            if not self._requested:
                self._output_dir.mkdir(parents=True, exist_ok=True)
                (self._output_dir / "tool-inventory.json").write_text(
                    json.dumps(sorted(available)),
                    encoding="utf-8",
                )
            ordered = [
                *_FIRST_TOOLS,
                *(n for n in available if n not in ("reset", "finish")),
                "reset",
                "finish",
            ]
            name = next(
                (n for n in ordered if n in available and n not in self._requested),
                "finish" if "finish" in available else next(iter(available)),
            )
            self._requested.add(name)

        instruction = self._instruction_for(name)
        messages = payload.get("messages") or []
        rest = [m for m in messages if m.get("role") != "system"]
        last_assistant = max(
            (idx for idx, msg in enumerate(rest) if msg.get("role") == "assistant"),
            default=None,
        )
        tail = [dict(msg) for msg in rest[last_assistant:]] if last_assistant is not None else []
        if tail and tail[-1].get("role") == "user":
            content = tail[-1].get("content")
            if isinstance(content, list):
                tail[-1]["content"] = [*content, {"type": "text", "text": instruction}]
            else:
                prefix = str(content) if content else ""
                tail[-1]["content"] = (
                    f"{prefix}\n{instruction}" if prefix else instruction
                )
        else:
            tail.append({"role": "user", "content": instruction})

        rewritten = dict(payload)
        rewritten["messages"] = [
            {"role": "system", "content": self._role_prompt},
            *tail,
        ]
        rewritten["tools"] = [available[name]]
        rewritten["parallel_tool_calls"] = False
        rewritten["tool_choice"] = "auto" if name == "finish" else "required"
        return rewritten

    def _instruction_for(self, name: str) -> str:
        parts = [f"Call {name} using its schema."]
        if name in self._examples:
            parts.append(
                "Use these exact bounded arguments: "
                + json.dumps(self._examples[name])
                + "."
            )
        else:
            parts.append(
                "Set max_chunks, chunks and n_action_steps to 1 when offered."
            )
        if name == "list_dir":
            parts.append(f"List this directory: {self._output_dir}.")
        elif name in ("write_text_file", "read_text_file"):
            parts.append(f"Use file path: {self._output_dir}/probe.txt.")
        elif name == "read_image":
            images = sorted(self._output_dir.glob("*.png/00.png"))
            if images:
                parts.append(f"Read {images[0].parent.name} at step 0.")
        elif name == "finish":
            parts.append("All tools have been exercised. Call finish now.")
        return " ".join(parts)

    def _forward(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length) if length > 0 else None
        path = handler.path
        if path.startswith("/v1"):
            path = path[3:]
        target_url = f"{self._upstream_url}{path}"

        if method == "POST" and path.rstrip("/").endswith("/chat/completions") and body:
            payload = json.loads(body.decode("utf-8"))
            body = json.dumps(self.rewrite_request(payload)).encode("utf-8")

        headers: dict[str, str] = {}
        for header in ("Content-Type", "Authorization", "Accept"):
            value = handler.headers.get(header)
            if value:
                headers[header] = value
        if body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            target_url, data=body, headers=headers, method=method
        )
        try:
            with self._opener.open(req, timeout=self._timeout_s) as resp:
                resp_body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/json")
                self._send_raw(handler, resp.status, content_type, resp_body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read()
            content_type = exc.headers.get("Content-Type", "application/json")
            self._send_raw(handler, exc.code, content_type, err_body)
        except Exception as exc:  # noqa: BLE001 - surfaced to the local CLI client
            err_body = json.dumps({"error": {"message": str(exc)}}).encode("utf-8")
            self._send_raw(handler, 502, "application/json", err_body)

    @staticmethod
    def _send_raw(
        handler: BaseHTTPRequestHandler,
        status: int,
        content_type: str,
        body: bytes,
    ) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(body)
