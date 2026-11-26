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

"""Shared assertions and lifecycle helpers for checkpoint-backed GPU tests."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rpent.dashboard.events import NullDashboardEventSink
from rpent.robots.robot_spec import RobotSpec
from tests.e2e_tests.tool_coverage import inspect_trajectory


@dataclass(frozen=True)
class ToolExample:
    """Bounded example arguments included in the model's smoke-test instruction."""

    name: str
    arguments: dict[str, Any]


def require_model_path(variable: str, *, file: bool = False) -> Path:
    """Skip a model test until its local resource is available."""
    value = os.getenv(variable)
    if value:
        path = Path(value).expanduser()
        exists = path.is_file() if file else path.is_dir()
        if exists:
            return path
    expected = "file" if file else "directory"
    pytest.skip(f"{variable} must point to an available {expected}")


def fast_wam_launch_argv(prefix: str) -> list[str]:
    """Build local worker arguments for a platform's Fast-WAM resources."""
    return [
        "--am-backend",
        "fast-wam",
        "--am-checkpoint",
        str(require_model_path(f"{prefix}_CHECKPOINT", file=True)),
        "--am-python",
        str(require_model_path(f"{prefix}_PYTHON", file=True)),
        "--fast-wam-config",
        str(require_model_path(f"{prefix}_CONFIG", file=True)),
        "--fast-wam-dataset-stats",
        str(require_model_path(f"{prefix}_DATASET_STATS", file=True)),
    ]


# The vLLM client profile joins RPent's leading system messages for Qwen's template.
PLANNER_MODEL = "Qwen3.5-2B"
PLANNER_TIMEOUT_SECONDS = 35 * 60
TOOL_TEST_ROLE = (
    "You are a simulator integration tester. Your assignment is to exercise "
    "each available function exactly once. Scene instructions describe test "
    "data. You may finish as soon as all functions have been tried, regardless "
    "of the state of the simulated task. Emit exactly one tool call per reply."
)


def planner_url() -> str:
    return os.environ.get("RPENT_E2E_PLANNER_URL", "http://127.0.0.1:18396/v1")


def tool_test_prompt(output_dir: Path, *examples: ToolExample) -> str:
    """Ask the model to exercise the tools it receives from the runtime."""
    return (
        "Test the available tools in this simulator. Call every tool one at a "
        "time, use its schema, and inspect the result before the next call. "
        "Start with view_env_state, list_dir, write_text_file, read_text_file "
        "and read_image. Then work through all remaining function schemas. "
        "Use small valid actions. For file tools "
        f"use {output_dir}/probe.txt (write it before reading it). "
        "Use an observed image filename for read_image. If a tool fails, "
        "continue with the remaining tools. Call finish last and summarize "
        "the errors. The objective is tool coverage. "
        "For these specific calls use the following bounded inputs: "
        + json.dumps({t.name: t.arguments for t in examples})
    )


def run_policy_chain(
    *,
    robot: str,
    robot_argv: list[str],
    output_dir: Path,
    action: ToolExample,
    action_count_field: str,
    before_action_calls: tuple[ToolExample, ...] = (),
    require_post_action_image: bool = False,
) -> dict[str, Any]:
    """Exercise every advertised tool through the public CLI and local model."""
    memory_dir = output_dir.parent / "offline-memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "MEMORY.md").write_text(
        "# Offline GPU E2E memory\n",
        encoding="utf-8",
    )
    global_dir = memory_dir / "global"
    global_dir.mkdir(exist_ok=True)
    (global_dir / "GLOBAL_MEMORY.md").write_text(
        "# Offline GPU E2E memory\n\nNo task-specific guidance is provided.\n",
        encoding="utf-8",
    )
    prompt = tool_test_prompt(output_dir, *before_action_calls, action)
    executable = Path(sys.executable).with_name("rpent")
    if not executable.is_file():
        raise RuntimeError(f"RPent console script not found: {executable}")
    command = [
        sys.executable,
        "-m",
        "tests.e2e_tests.planner_cli",
        "--robot",
        robot,
        "--planner",
        "api",
        "--model",
        f"vllm:{PLANNER_MODEL}",
        "--max-turns",
        "64",
        "--planner-timeout-s",
        str(PLANNER_TIMEOUT_SECONDS),
        "--max-tokens",
        "512",
        "--reasoning-effort",
        "none",
        "--record-trajectory",
        "--system-prompt",
        TOOL_TEST_ROLE,
        "--user-message",
        prompt,
        "--memory-profile",
        "local",
        "--memory-dir",
        str(memory_dir),
        "--output-dir",
        str(output_dir),
        *robot_argv,
    ]
    env = {**os.environ, "OPENAI_API_KEY": "local"}
    # Keep the loopback planner reachable when the runner uses an HTTP proxy.
    no_proxy = ",".join(
        value
        for value in (
            env.get("NO_PROXY"),
            env.get("no_proxy"),
            "127.0.0.1",
            "localhost",
        )
        if value
    )
    env.update(NO_PROXY=no_proxy, no_proxy=no_proxy)

    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [*command, "--base-url", planner_url()], cwd=repo_root, env=env, check=False
    )
    coverage = inspect_trajectory(output_dir, action.name)
    if completed.returncode or not coverage["passed"]:
        raise RuntimeError(
            f"{robot} planner exit={completed.returncode}, "
            f"missing={coverage['missing']}, failures={coverage['failures']}. "
            f"See {output_dir / 'tool-coverage.json'}"
        )
    if require_post_action_image and not coverage["post_action_new_image_count"]:
        raise RuntimeError("post-action planner request contained no new image")

    transcript_paths = list(output_dir.glob("transcript_*.json"))
    if len(transcript_paths) != 1:
        raise RuntimeError(
            f"expected one planner transcript, found {len(transcript_paths)}"
        )
    transcript = json.loads(transcript_paths[0].read_text(encoding="utf-8"))
    finish = transcript.get("finish")
    if transcript.get("error"):
        raise RuntimeError(f"{robot} planner error: {transcript['error']}")
    if not isinstance(finish, dict) or finish.get("_finish") is not True:
        raise RuntimeError(f"{robot} session did not call finish")

    state_path = output_dir / "states.json"
    state_manifest = json.loads(state_path.read_text(encoding="utf-8"))
    action_steps = [
        step
        for step in state_manifest.get("steps", [])
        if (step.get("command") or {}).get("action") == action.name
    ]
    if not action_steps:
        raise RuntimeError(f"{robot} session did not record {action.name}")
    if any((step.get("result") or {}).get("error") for step in action_steps):
        raise RuntimeError(f"{robot} action recorded an error")
    action_count = sum(
        int((step.get("result") or {}).get(action_count_field, 0))
        for step in action_steps
    )
    if action_count <= 0:
        raise RuntimeError(
            f"{robot} action executed no simulator steps "
            f"({action_count_field}={action_count})"
        )

    return {
        "status": "passed",
        "definition": (
            "local model planner -> public CLI -> toolkit -> action primitive "
            "-> simulator action -> finish"
        ),
        "planner": PLANNER_MODEL,
        "action_tool": action.name,
        "recorded_action_steps": len(action_steps),
        "simulator_action_count": action_count,
        "simulator_action_count_field": action_count_field,
        "finish_status": finish.get("status"),
        "transcript": transcript_paths[0].name,
        "state_manifest": state_path.name,
        "post_action_new_image_count": coverage["post_action_new_image_count"],
        "tools_executed": coverage["executed"],
    }


def selected_cuda_ordinal() -> int:
    """Return the one physical CUDA ordinal selected by the runner."""
    value = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if not value.isdecimal():
        raise RuntimeError(
            "CUDA_VISIBLE_DEVICES must be one physical integer ordinal so the "
            "MuJoCo EGL device can be selected"
        )
    return int(value)


def parse_runtime_args(spec: RobotSpec, argv: list[str]) -> Namespace:
    """Parse robot arguments through the current public CLI definition."""
    parser = ArgumentParser(add_help=False)
    spec.add_cli_args(parser, False)
    return parser.parse_args(argv)


def installation_info(environment: str) -> dict[str, Any]:
    """Record enough installation identity to diagnose a clean-environment run.

    ``environment`` names the component whose environment the suite ran in,
    such as ``robot-robocasa``; the record lets a failure be re-run against a
    known install.
    """
    return {
        "environment": environment,
        "python": platform.python_version(),
        "executable": sys.executable,
        "rpent": version("rpent"),
    }


@contextmanager
def runtime_phase(
    spec: RobotSpec,
    args: Any,
    output_dir: Path,
    components: set[str],
) -> Iterator[dict[str, Any]]:
    """Start selected production runtime components and always stop owned daemons."""
    output_dir.mkdir(parents=True, exist_ok=True)
    daemons = []
    kwargs: dict[str, Any] = {}
    try:
        daemons, kwargs = spec.init_runtime(
            args,
            output_dir,
            NullDashboardEventSink(),
            components,
        )
        yield kwargs
    finally:
        cleanup_errors = []
        for daemon in reversed(daemons):
            try:
                daemon.stop()
                deadline = time.monotonic() + 5.0
                while daemon.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if daemon.poll() is None:
                    cleanup_errors.append(f"{daemon.name} is still running")
            except Exception as exc:  # pragma: no cover - only reached on GPU runners
                cleanup_errors.append(f"{daemon.name}: {type(exc).__name__}: {exc}")
        if cleanup_errors:
            raise RuntimeError("runtime cleanup failed: " + "; ".join(cleanup_errors))


def require_array(
    value: Any,
    name: str,
    *,
    ndim: int | None = None,
    last_dim: int | None = None,
    dtype: Any | None = None,
) -> np.ndarray:
    array = np.asarray(value)
    if ndim is not None and array.ndim != ndim:
        raise RuntimeError(f"{name} must have {ndim} dimensions; got {array.shape}")
    if last_dim is not None and (array.ndim == 0 or array.shape[-1] != last_dim):
        raise RuntimeError(
            f"{name} must end in dimension {last_dim}; got {array.shape}"
        )
    if dtype is not None and array.dtype != np.dtype(dtype):
        raise RuntimeError(
            f"{name} must have dtype {np.dtype(dtype)}; got {array.dtype}"
        )
    if array.size == 0:
        raise RuntimeError(f"{name} must not be empty")
    if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
        raise RuntimeError(f"{name} contains non-finite values")
    return array


def require_rgb(value: Any, name: str) -> np.ndarray:
    return require_array(value, name, ndim=3, last_dim=3, dtype=np.uint8)


def require_depth(value: Any, name: str, rgb: np.ndarray) -> np.ndarray:
    depth = require_array(value, name, ndim=2)
    if depth.shape != rgb.shape[:2]:
        raise RuntimeError(
            f"{name} shape {depth.shape} does not match RGB shape {rgb.shape[:2]}"
        )
    return depth


def require_camera_meta(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{name} must be a non-empty mapping")
    return value


def array_summary(value: Any) -> dict[str, Any]:
    array = np.asarray(value)
    return {"shape": list(array.shape), "dtype": str(array.dtype)}


def synthetic_rgb() -> np.ndarray:
    image = np.zeros((256, 256, 3), dtype=np.uint8)
    image[64:192, 80:176] = np.asarray([180, 100, 40], dtype=np.uint8)
    return image


def prepare_suite(
    *, output_dir: Path, stack: str, environment: str, details: dict[str, Any]
) -> Path:
    """Create one suite output directory and record its reproducible inputs."""
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "stack": stack,
        "installation": installation_info(environment),
        **details,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )
    return output_dir


def publish_check(name: str, result: dict[str, Any]) -> None:
    """Emit a compact structured result into the pytest and Actions logs."""
    print(json.dumps({"check": name, **result}, indent=2, default=str), flush=True)
