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

"""Scene family: observation entry points over a persisted EnvState.

The family owns the projection from recorded artifacts to the observation
contract. Localization is a separate family in ``toolkits/geometry`` so the
core does not import a toolkit package.
"""

from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, Mapping, Sequence

import numpy as np
from pydantic import Field

from rpent.tools.base import Tool, ToolResult, tool
from rpent.tools.capabilities import Capabilities, ToolFamily
from rpent.tools.observation import Observation, ObservationError
from rpent.tools.world_coordinates import artifact_name, query_world_map

if TYPE_CHECKING:
    from rpent.session import EnvState, StepRecord

_RGB_PRIORITY = ("head_camera", "head", "agentview", "left_wrist", "right_wrist")


def _array(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float64)


def _camera_meta(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _first(meta: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in meta:
            return meta[key]
    return None


class EnvStateObservationProvider:
    """Load one view of one recorded step through the geometry contract.

    Camera conventions are detected from the calibration keys; a host can
    override them per view when a platform uses an ambiguous name.
    """

    def __init__(
        self,
        state: EnvState,
        *,
        default_view: str | None = None,
        camera_conventions: Mapping[str, str] | None = None,
        depth_units: Mapping[str, str] | None = None,
    ) -> None:
        self._state = state
        self._default_view = default_view
        self._conventions = dict(camera_conventions or {})
        self._depth_units = dict(depth_units or {})

    def _record(self, step: int | None) -> StepRecord:
        try:
            return self._state.get(-1 if step is None else int(step))
        except Exception as exc:
            raise ObservationError(
                "state_not_found",
                "the requested recorded step does not exist",
                step=-1 if step is None else int(step),
                detail=str(exc),
            ) from exc

    def views(self) -> Sequence[str]:
        try:
            record = self._record(-1)
        except ObservationError:
            return ()
        specs = record.state.get("view_specs") or {}
        return tuple(specs) if isinstance(specs, Mapping) else ()

    def default_view(self) -> str | None:
        if self._default_view is not None:
            return self._default_view
        views = self.views()
        return views[0] if views else None

    def observe(
        self, *, view: str | None = None, step: int | None = None
    ) -> Observation:
        record = self._record(step)
        specs = record.state.get("view_specs") or {}
        if not isinstance(specs, Mapping) or not specs:
            raise ObservationError(
                "no_views",
                "this state has no recorded camera views",
                step=record.step_idx,
            )
        view = view or self.default_view()
        if view not in specs:
            raise ObservationError(
                "view_not_found",
                "the requested view is unavailable in this state",
                view=view,
                available_views=sorted(specs),
                step=record.step_idx,
            )
        available = record.artifacts
        image_shape = tuple(int(value) for value in specs[view]["image_shape"])
        rgb_name = artifact_name(view, "rgb")
        if rgb_name not in available:
            raise ObservationError(
                "rgb_not_found",
                "the view has no recorded RGB image",
                view=view,
                step=record.step_idx,
            )
        rgb = np.asarray(self._state.load(rgb_name, step=record.step_idx))
        image_shape = tuple(int(value) for value in rgb.shape[:2])
        depth = self._load_array(view, "depth", record, image_shape)
        world_xyz = self._load_array(view, "world_xyz", record, image_shape)
        meta = self._load_meta(view, record)

        depth_unit = self._depth_units.get(view) or str(
            meta.get("depth_unit") or "metre"
        )
        if depth is not None:
            depth = self._metric_depth(depth, meta)

        intrinsics = _array(_first(meta, ("intrinsic_K", "intrinsics", "K")))
        if intrinsics is not None and intrinsics.shape != (3, 3):
            intrinsics = None
        world_from_camera = _array(
            _first(
                meta,
                (
                    "cam2world_cv",
                    "cam2world_gl",
                    "world_from_camera",
                    "extrinsic_cam2world",
                ),
            )
        )
        if world_from_camera is not None and world_from_camera.shape != (4, 4):
            world_from_camera = None
        convention = self._conventions.get(view)
        if convention is None:
            convention = "opengl" if "cam2world_gl" in meta else "opencv"
        return Observation(
            view=str(view),
            step=record.step_idx,
            image_shape=image_shape,
            rgb=rgb,
            depth=depth,
            world_xyz=world_xyz,
            intrinsics=intrinsics,
            world_from_camera=world_from_camera,
            camera_convention=convention,
            depth_unit=depth_unit,
            metadata=meta,
        )

    def _load_array(
        self,
        view: str,
        field: str,
        record: StepRecord,
        image_shape: tuple[int, int],
    ) -> np.ndarray | None:
        name = artifact_name(view, field)
        if name not in record.artifacts:
            return None
        try:
            value = np.asarray(
                self._state.load(name, step=record.step_idx), dtype=np.float64
            )
        except Exception as exc:
            raise ObservationError(
                "artifact_invalid",
                f"the recorded {field} artifact cannot be read",
                view=view,
                step=record.step_idx,
                detail=str(exc),
            ) from exc
        if field == "depth":
            if value.ndim == 3 and value.shape[2] == 1:
                value = value[..., 0]
            if value.shape != image_shape:
                return None
            return value
        if value.shape != (*image_shape, 3):
            return None
        return value

    def _load_meta(self, view: str, record: StepRecord) -> dict[str, Any]:
        name = artifact_name(view, "camera_meta")
        if name not in record.artifacts:
            return {}
        try:
            return _camera_meta(self._state.load(name, step=record.step_idx))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _metric_depth(depth: np.ndarray, meta: Mapping[str, Any]) -> np.ndarray:
        """Convert normalized depth when the camera reports near and far planes."""
        near = meta.get("depth_near")
        far = meta.get("depth_far")
        if near is None or far is None:
            return depth
        near_f, far_f = float(near), float(far)
        if not (0 < near_f < far_f):
            return depth
        denominator = 1.0 - depth * (1.0 - near_f / far_f)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(depth > 0, near_f / denominator, np.nan)


@tool(readonly=True, exclude=("state",))
def view_env_state(
    step: Annotated[int, Field(json_schema_extra={"default": -1})] = -1,
    *,
    state: EnvState,
) -> ToolResult:
    """Read one recorded EnvState step and its synchronized camera views. Step -1 selects the latest entry. Embeds up to four RGB views labeled name@step. Read-only.

    Args:
        step: Step number; 0 = initial, -1 = latest.
    """
    images: list[bytes] = []
    labels: list[str] = []
    try:
        record = state.get(step)
    except Exception as error:
        return ToolResult(data={"error": f"state step not available: {error}"})
    specs = record.state.get("view_specs") or {}
    views = list(specs) if isinstance(specs, Mapping) else []
    ordered = [name for name in _RGB_PRIORITY if name in views]
    ordered.extend(name for name in views if name not in ordered)
    result: dict[str, Any] = {
        "step": record.step_idx,
        "terminated": record.terminated,
        "truncated": record.truncated,
        "state": record.state,
        "artifacts": sorted(record.artifacts),
        "task_language": record.extras.get("task_language"),
        "views": {
            name: {
                "image_shape": specs[name].get("image_shape"),
                "pixel_order": specs[name].get("pixel_order", "row_col"),
            }
            for name in views
        },
    }
    result["log"] = {
        "command": record.command,
        "result": record.result,
        "elapsed_s": record.elapsed_s,
    }
    for view in ordered[:4]:
        name = artifact_name(view, "rgb")
        if name not in record.artifacts:
            continue
        try:
            images.append(state.load_bytes(name, step=record.step_idx))
        except FileNotFoundError:
            continue
        labels.append(f"{view}@step{record.step_idx}")
    return ToolResult(data=result, images=images, image_labels=labels)


class SceneTools(ToolFamily):
    """Observation and world-map tools bound to one recorded EnvState."""

    name = "scene"

    def __init__(self, *, state: EnvState) -> None:
        self._state = state

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        # ``query_world_map`` reads a saved world-map artifact, not a depth
        # view. Whether that artifact exists is known only when the call runs,
        # so the tool reports a structured error instead of being trimmed by
        # an unrelated depth capability.
        return (
            view_env_state.with_handler(partial(view_env_state, state=self._state)),
            query_world_map.with_handler(
                partial(query_world_map, env_state=self._state)
            ),
        )


__all__ = [
    "EnvStateObservationProvider",
    "SceneTools",
    "view_env_state",
]
