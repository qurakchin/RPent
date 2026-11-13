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

"""RPent tools for the RLinf RoboTwin robot."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from robots.robotwin.motion import RoboTwinMotionBackend
from robots.robotwin.observation import dump_observation, world_from_depth
from robots.robotwin.policy import RoboTwinPolicyBinding
from robots.robotwin.primitives import RoboTwinPrimitives
from robots.robotwin.robot_spec import ROBOTWIN_CAMERA_NAMES, env_runtime_contract
from rpent.dashboard.events import DashboardEventSink
from rpent.session import EnvState
from rpent.session.env_capture import CapturingEnvClient
from rpent.tools import Tool, ToolResult, iter_tools, tool
from rpent.tools.capabilities import Capabilities
from rpent.tools.direct_action import direct_action_tool
from rpent.tools.memory_tools import MemoryTools
from rpent.tools.motion_tools import MotionTools
from rpent.tools.policy_tools import PolicyConfig, PolicyTools
from rpent.tools.scene_tools import (
    EnvStateObservationProvider,
    MolmoGrounder,
    Sam3Segmenter,
    SceneTools,
    view_env_state,
)
from rpent.tools.toolkit import Toolkit
from rpent.utils.logging import get_output_dir
from toolkits.geometry.tool import GeometryToolConfig, GeometryTools

if TYPE_CHECKING:
    from robots.robotwin.env_client import RoboTwinEnvClient
    from rpent.memory.manager import MemoryManager

# State-advancing RoboTwin primitives eligible for the recipe. ``reset``,
# ``render``, and read-only tools are intentionally excluded so the recipe
# records only commands that actually move the robot.
_RECIPE_ACTIONS = {
    "wam_act",
    "lingbot_act",
    "execute_action",
    "move_to",
    "rotate_wrist",
    "set_gripper",
    "release",
}


def _declared_views(
    server_meta: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the depth and calibrated camera views advertised by the server."""
    extensions = server_meta.get("extensions")
    extensions = extensions if isinstance(extensions, dict) else {}
    render_camera = extensions.get("render_camera")
    render_camera = render_camera if isinstance(render_camera, dict) else {}
    names = tuple(render_camera.get("camera_names") or ())
    depth_views = names if render_camera.get("metric_depth") is True else ()
    calibrated_views = names if extensions.get("get_camera_meta") is True else ()
    return depth_views, calibrated_views


class RoboTwinToolkit(Toolkit):
    """Common RPent tools plus RoboTwin primitives."""

    def __init__(
        self,
        *,
        runtime_kwargs: dict[str, Any],
        dashboard_events: DashboardEventSink,
        memory: MemoryManager,
        enable_direct_action: bool = False,
        mode: str = "evaluation",
        attempts_per_session: int = 0,
        state_output_dir: Path | str | None = None,
    ):
        if mode not in {"evaluation", "exploration"}:
            raise ValueError(f"unsupported RoboTwin toolkit mode: {mode!r}")
        state = EnvState(Path(state_output_dir or get_output_dir()))
        super().__init__(
            dashboard_events=dashboard_events,
            state=state,
            memory=memory,
        )
        self._mode = mode
        self._policy_kind = runtime_kwargs.get("policy_kind", "vla")
        self._attempt = 1
        self._attempts_per_session = max(0, int(attempts_per_session))
        self._latest_status: dict[str, Any] = {}
        if self._mode == "evaluation":
            env = runtime_kwargs["env"]
            runtime_kwargs = {
                **runtime_kwargs,
                "env": CapturingEnvClient(
                    env,
                    state,
                    capture_call=partial(_capture_robotwin_call, env),
                ),
            }
        self._primitives = RoboTwinPrimitives(
            check_cancelled=self.raise_if_cancelled,
            **runtime_kwargs,
        )
        if self._mode == "exploration":
            reset_result = self._primitives.reset()
        else:
            # The environment service has already initialized this episode.
            if self._policy_kind == "wam":
                self._primitives.model.reset()
            reset_result = {
                **self._primitives.env.last_reset_info,
                "success": True,
            }
        self._primitives.start_recording()
        self._action_frame_cursor = self._primitives.recorded_frame_count()
        self._register_families(runtime_kwargs)
        self._register_robotwin_tools()
        if enable_direct_action:
            self.add_tool(
                direct_action_tool(
                    self._primitives.env.action_specs,
                    partial(self._step, "execute_action"),
                )
            )
        initial = self.get_env_state(
            command={"action": "reset"},
            result=reset_result,
            elapsed_s=0.0,
        )
        record = self._state.latest_record()
        if record is not None:
            self._publish_step(record)
        initial_state = initial.data.get("state")
        if isinstance(initial_state, dict):
            self._latest_status = initial_state.get(
                "episode_status", self._latest_status
            )

    def _register_families(self, runtime_kwargs: dict[str, Any]) -> None:
        molmo = runtime_kwargs.get("molmo_client")
        sam3 = runtime_kwargs.get("sam3_client")
        grounder = MolmoGrounder(molmo) if molmo is not None else None
        segmenter = Sam3Segmenter(sam3) if sam3 is not None else None
        binding = RoboTwinPolicyBinding(self._primitives)
        server_meta = dict(getattr(self._primitives.env, "server_meta", {}) or {})
        views, calibrated_views = _declared_views(server_meta)
        self._capabilities = Capabilities(
            env=server_meta,
            execution=dict(
                getattr(self._primitives.env, "execution_capabilities", {}) or {}
            ),
            segmentation=segmenter is not None,
            grounding=grounder is not None,
            policy_backends=(binding.backend,),
            real_robot=False,
            depth_views=views,
            calibrated_views=calibrated_views,
            native_tools=("execute_action", "finish", "render", "reset"),
        )
        provider = EnvStateObservationProvider(
            self._state,
            default_view="head",
            camera_conventions=dict.fromkeys(views, "opengl"),
        )
        self.add_tools(
            SceneTools(state=self._state),
            GeometryTools(
                provider=provider,
                grounder=grounder,
                segmenter=segmenter,
                config=GeometryToolConfig(),
            ),
            MotionTools(RoboTwinMotionBackend(self._primitives)),
            PolicyTools(
                binding,
                config=PolicyConfig(use_length=binding.use_length),
            ),
            MemoryTools(self._memory),
            capabilities=self._capabilities,
            config={"mode": self._mode},
        )

    @classmethod
    def declared_tools(cls, *, policy_kind: str = "vla") -> list[Tool]:
        """Collect declarations without constructing an environment.

        The registration path binds handlers to one instance; this snapshot is
        used by offline schema checks and documentation tooling.
        """
        from rpent.tools.motion_tools import MotionTools
        from rpent.tools.policy_tools import PolicyTools
        from rpent.tools.scene_tools import view_env_state
        from rpent.tools.world_coordinates import query_world_map

        views, calibrated_views = _declared_views(
            env_runtime_contract(
                task_name="declared", task_config="declared", seed=0
            )
        )
        geometry = GeometryTools(provider=object()).tools(
            Capabilities(
                depth_views=views,
                calibrated_views=calibrated_views,
                grounding=False,
            )
        )
        policy = iter_tools(PolicyTools)
        policy_name = "wam_act" if policy_kind == "wam" else "lingbot_act"
        return [
            view_env_state,
            *geometry,
            query_world_map,
            *iter_tools(MotionTools),
            next(item for item in policy if item.name == policy_name),
            *iter_tools(MemoryTools),
            *iter_tools(RoboTwinPrimitives),
            cls.render,
        ]

    def _register_robotwin_tools(self) -> None:
        for definition in iter_tools(self._primitives):
            self.add_tool(definition, replace=True)
        self.add_tool(self.render)
        if self._mode == "exploration":
            self.add_tool(
                self._primitives.finish.with_handler(self._guarded_finish), replace=True
            )
            self.add_tool(self._reset_episode)

    @tool
    def render(self) -> ToolResult:
        """Capture a fresh synchronized RoboTwin agent observation."""
        self.raise_if_cancelled()
        return ToolResult(data={"success": True})

    def _guarded_finish(self, *, status: str, summary: str) -> ToolResult:
        budget = self._attempts_per_session
        if budget and not self.solved() and self._attempt < budget:
            payload = {
                "error": "finish refused",
                "reason": (
                    f"This session has {budget - self._attempt} of its {budget} "
                    "attempts left. Archive the attempt, reset, and change the plan."
                ),
            }
            return ToolResult(data=payload)
        return self._primitives.finish(status=status, summary=summary)

    @tool(name="reset")
    def _reset_episode(self) -> ToolResult:
        """Restart the episode for a fresh exploration attempt. Available only in explore mode. Re-run perception after every reset."""
        if self.solved():
            payload = {
                "error": "reset refused",
                "reason": "The task is already solved; save artifacts and finish.",
            }
            return ToolResult(data=payload)
        budget = self._attempts_per_session
        if budget and self._attempt >= budget:
            payload = {
                "error": "reset refused",
                "reason": (
                    f"This session's attempt budget is spent ({budget} attempts). "
                    "Update the handoff notes and finish this session."
                ),
            }
            return ToolResult(data=payload)
        result = self._primitives.reset()
        if result.get("error") or result.get("success") is False:
            payload = result
            return ToolResult(data=payload)
        self._attempt += 1
        payload = {
            **result,
            "attempt": self._attempt,
            "notice": "Fresh episode started. Re-run perception before acting.",
        }
        return ToolResult(data=payload)

    def _capture_full_observation(self) -> dict[str, Any]:
        """Assemble rgb, depth, calibration, and world maps for one state.

        These artifacts feed ``view_env_state`` and ``geometry``. Policy
        inference builds a lighter RGB-only observation in the policy binding.
        """
        env = self._primitives.env
        views: dict[str, dict[str, Any]] = {}
        for camera_name in ROBOTWIN_CAMERA_NAMES:
            rendered = env.render_camera(camera_name, depth=True)
            if not isinstance(rendered, (list, tuple)) or len(rendered) != 2:
                raise TypeError(
                    "RoboTwin render_camera(depth=True) must return (rgb, depth)"
                )
            rgb, depth = rendered
            camera_meta = env.get_camera_meta(camera_name)
            views[camera_name] = {
                "rgb": np.asarray(rgb),
                "depth": np.asarray(depth, dtype=np.float32),
                "world_xyz": world_from_depth(depth, camera_meta),
                "camera_meta": camera_meta,
            }
        return {
            "views": views,
            "robot_state": env.last_info["robot_state"],
            "task_name": env.server_meta["task_name"],
            "task_language": env.get_task_language(),
            "depth_unit": "metres",
            "world_frame": "world",
        }

    def get_env_state(
        self,
        *,
        command: dict[str, Any],
        result: dict[str, Any],
        elapsed_s: float,
    ) -> ToolResult:
        frame_start = self._action_frame_cursor
        self._action_frame_cursor = self._primitives.recorded_frame_count()
        status = self._primitives.status()
        self._latest_status = status
        observation = self._capture_full_observation()
        record = dump_observation(
            observation,
            env_state=self._state,
            status=status,
            log={
                "command": command,
                "result": result,
                "elapsed_s": elapsed_s,
            },
        )
        if self._dashboard_events.enabled:
            frames = self._primitives.frame_slice(frame_start)
            if frames:
                self._state.save(
                    f"action_{command['action']}.mp4",
                    frames,
                    step=record.step_idx,
                    fps=20,
                )
        return view_env_state(record.step_idx, state=self._state)

    def close(self) -> None:
        """Flush the per-step frame buffer into ``episode.mp4`` (LIBERO parity)."""
        super().close()
        frames = self._primitives.stop_recording()
        if frames:
            self._state.save("episode.mp4", frames, step=None, fps=20)

    def solved(self) -> bool:
        """Return the native RoboTwin task success flag."""
        return self._primitives.status().get("eval_success") is True

    def _step(self, name: str, **kwargs) -> ToolResult:

        self.raise_if_cancelled()
        return getattr(self._primitives, name)(**kwargs)

    def write_recipe(self, recipe_tag: str) -> str:
        """Export state-advancing RoboTwin primitives with no error and no
        explicit ``success=False`` from ``EnvState.records()``."""
        records = self._state.records()
        if self._mode == "exploration":
            if not self.solved():
                return ""
            last_reset = max(
                (
                    record.step_idx
                    for record in records
                    if isinstance(record.command, dict)
                    and record.command.get("action") == "reset"
                    and not (
                        isinstance(record.result, dict) and record.result.get("error")
                    )
                ),
                default=-1,
            )
            records = [record for record in records if record.step_idx > last_reset]
            if not any(record.terminated for record in records):
                return ""
        recipe = [
            record.command
            for record in records
            if isinstance(record.command, dict)
            and record.command.get("action") in _RECIPE_ACTIONS
            and not (
                isinstance(record.result, dict)
                and (
                    record.result.get("error") or record.result.get("success") is False
                )
            )
        ]
        name = f"{recipe_tag}_recipe.jsonl"
        destination = (
            EnvState(Path(get_output_dir()))
            if self._mode == "exploration"
            else self._state
        )
        saved = destination.save(name, recipe, step=None)
        if saved is None:
            raise RuntimeError(f"failed to save RoboTwin recipe artifact: {name}")
        return str(destination.artifact_path(name, step=None))


def _capture_robotwin_call(
    env: RoboTwinEnvClient,
    method: Literal["step", "chunk_step"],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a RoboTwin call and extract its capture data."""
    if args:
        (actions,) = args
    else:
        actions = kwargs.pop("action" if method == "step" else "actions")
    array = np.atleast_2d(np.asarray(actions, dtype=np.float64))
    if method == "step" and len(array) != 1:
        raise ValueError("RoboTwin common action must be a single action")
    return_all_frames = (
        kwargs.pop("return_all_frames", False) if method == "chunk_step" else False
    )
    obs, rewards, terminated, truncated, info = env.chunk_step(
        array, return_all_frames=True, **kwargs
    )
    before = info.pop("before_observation")
    if method == "step":
        result = (
            obs["final"],
            float(rewards[0]),
            bool(terminated[0]),
            bool(truncated[0]),
            info,
        )
    else:
        result = (
            obs if return_all_frames else obs["final"],
            rewards,
            terminated,
            truncated,
            info,
        )

    def observation_payload(observation):
        return {
            "format": "robotwin.observation",
            "data": observation,
            "completeness": "complete",
            "inline_array_paths": tuple(
                f"/robot_state/{key}" for key in observation["robot_state"]
            ),
        }

    return {
        "result": result,
        "before_observation": observation_payload(before),
        "steps": [
            {
                "action": {
                    "format": f"robotwin.action.{info['action_type']}",
                    "data": array[index].copy(),
                    "completeness": "complete",
                    "inline_array_paths": ("",),
                },
                "after_observation": observation_payload(obs["frames"][index]),
                "result": {
                    "format": "robotwin.step_result",
                    "data": {
                        "reward": float(rewards[index]),
                        "terminated": bool(terminated[index]),
                        "truncated": bool(truncated[index]),
                        "info": info["per_step"][index],
                    },
                    "completeness": "complete",
                },
            }
            for index in range(info["executed_actions"])
        ],
    }
