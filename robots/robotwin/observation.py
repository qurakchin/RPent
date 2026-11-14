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

"""Model-independent views, artifacts, and joint state for RoboTwin."""

from typing import Any

import numpy as np

from rpent.robots.components.am_contracts import AMObservation
from rpent.session import EnvState, StepRecord
from rpent.tools.world_coordinates import artifact_name

ROBOTWIN_CAMERAS = ("head", "left_wrist", "right_wrist")


def world_from_depth(
    depth_metric: np.ndarray, camera_meta: dict[str, Any]
) -> np.ndarray:
    """Back-project metric depth into the RoboTwin world frame."""
    depth = np.asarray(depth_metric, dtype=np.float64)
    if depth.ndim != 2:
        raise ValueError(f"RoboTwin depth must have shape [H,W], got {depth.shape}")

    intrinsic = np.asarray(camera_meta.get("intrinsic_K"), dtype=np.float64)
    cam2world = np.asarray(camera_meta.get("cam2world_gl"), dtype=np.float64)
    if intrinsic.shape != (3, 3):
        raise ValueError("RoboTwin camera intrinsic_K must have shape (3,3)")
    if cam2world.shape != (4, 4):
        raise ValueError("RoboTwin camera cam2world_gl must have shape (4,4)")
    if not np.isfinite(intrinsic).all() or not np.isfinite(cam2world).all():
        raise ValueError("RoboTwin camera calibration must contain only finite values")

    height, width = depth.shape
    if camera_meta.get("height") != height or camera_meta.get("width") != width:
        raise ValueError(
            "RoboTwin depth shape does not match camera metadata: "
            f"depth={depth.shape}, metadata="
            f"({camera_meta.get('height')}, {camera_meta.get('width')})"
        )
    fx, fy = intrinsic[0, 0], intrinsic[1, 1]
    cx, cy = intrinsic[0, 2], intrinsic[1, 2]
    rows, cols = np.mgrid[0:height, 0:width]
    camera_points = np.stack(
        [
            (cols - cx) * depth / fx,
            -(rows - cy) * depth / fy,
            -depth,
        ],
        axis=-1,
    )
    world = camera_points @ cam2world[:3, :3].T + cam2world[:3, 3]
    return world.astype(np.float32)


def dump_observation(
    observation: dict[str, Any],
    *,
    env_state: EnvState,
    status: dict[str, Any],
    log: dict[str, Any] | None,
) -> StepRecord:
    """Persist one agent-visible observation without simulator oracle state."""
    step_idx = 0 if env_state.latest_step is None else env_state.latest_step + 1
    paths: dict[str, dict[str, str]] = {}
    view_specs: dict[str, dict[str, Any]] = {}
    for view_name, view in observation["views"].items():
        view_paths: dict[str, str] = {}
        if "rgb" in view:
            name = artifact_name(view_name, "rgb")
            view_paths["rgb"] = str(env_state.artifact_path(name, step=step_idx))
        for field in ("depth", "world_xyz"):
            if field in view:
                name = artifact_name(view_name, field)
                view_paths[field] = str(env_state.artifact_path(name, step=step_idx))
        if "camera_meta" in view:
            name = artifact_name(view_name, "camera_meta")
            view_paths["camera_meta"] = str(
                env_state.artifact_path(name, step=step_idx)
            )
        paths[view_name] = view_paths
        shape_source = next(
            (
                np.asarray(view[field])
                for field in ("rgb", "world_xyz", "depth")
                if field in view
            ),
            None,
        )
        if shape_source is not None and shape_source.ndim >= 2:
            view_specs[view_name] = {
                "coordinate_space": view_name,
                "image_shape": [
                    int(shape_source.shape[0]),
                    int(shape_source.shape[1]),
                ],
                "pixel_order": "row_col",
            }

    state = {
        "step_idx": step_idx,
        "task_name": observation["task_name"],
        "task_language": observation["task_language"],
        "robot_state": observation["robot_state"],
        "episode_status": status,
        "artifacts": paths,
        "view_specs": view_specs,
        "log": log,
    }
    eval_success = status.get("eval_success") is True
    with env_state.record_step(
        state=state,
        terminated=eval_success,
        truncated=False,
        command=(log or {}).get("command"),
        result=(log or {}).get("result"),
        elapsed_s=(log or {}).get("elapsed_s"),
        extras={"task_language": observation.get("task_language")},
    ) as recorded_step:
        for view_name, view in observation["views"].items():
            for field in ("rgb", "depth", "world_xyz", "camera_meta"):
                if field in view:
                    env_state.save(
                        artifact_name(view_name, field),
                        view[field],
                        step=recorded_step,
                    )
    return env_state.get(step_idx)


def physical_observation(observation: dict[str, Any]) -> AMObservation:
    """Keep native RGB orientation and the native joint-action vector.

    ``qpos_target14`` matches RoboTwin's ``joint_action.vector``: left arm's
    six joint targets and gripper, followed by the right arm's targets and
    gripper. These are controller setpoints, not measured joint positions.
    Camera resizing and state normalization belong to the model adapter.
    """
    native = observation["robot_state"]
    fields = {
        "qpos_target14": "joint_targets",
        "arm_qpos_real12": "joint_positions",
        "left_eef_pose": "left_eef_pose",
        "right_eef_pose": "right_eef_pose",
        "left_tcp_pose": "left_tcp_pose",
        "right_tcp_pose": "right_tcp_pose",
        "left_gripper": "left_gripper",
        "right_gripper": "right_gripper",
    }
    return {
        "images": {name: view["rgb"] for name, view in observation["views"].items()},
        "state": {
            target: np.atleast_1d(native[source])
            for source, target in fields.items()
            if source in native
        },
        "instruction": observation["task_language"],
    }
