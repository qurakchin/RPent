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

"""The single planner-facing localization tool.

``geometry`` answers "where is this target and how big is it": it selects a
pixel, segments it, back-projects the mask, fits a world-frame estimate, and
reports quality. Point selection, segmentation, and sampling remain internal
steps so callers cannot consume an intermediate value as a final answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import partial
from typing import Annotated, Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, create_model

from rpent.tools.base import Tool, ToolResult, tool
from rpent.tools.capabilities import Capabilities, ToolFamily
from rpent.tools.observation import (
    Grounder,
    Observation,
    ObservationError,
    ObservationProvider,
    Segmenter,
)
from toolkits.geometry.core import (
    GeometryConfig,
    depth_region_mask,
    fit_mask,
    observation_world_xyz,
)

Quantity = Literal["center", "extent", "z_range", "orientation"]
_QUANTITIES = ("center", "extent", "z_range", "orientation")


@dataclass(frozen=True)
class GeometryToolConfig:
    """Host configuration for localization quality and defaults."""

    quality: GeometryConfig = field(default_factory=GeometryConfig)
    default_quantities: tuple[Quantity, ...] = ("center", "extent")


def _error(status: str, code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "error": {"code": code, "message": message}, **details}


def _field(
    value: Any,
    *,
    unit: str,
    definition: str,
    evidence: str,
    refs: list[str],
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "definition": definition,
        "evidence_status": evidence,
        "source_refs": list(refs),
    }


def _pixel_in_bounds(pixel: tuple[int, int], observation: Observation) -> bool:
    row, col = pixel
    return 0 <= row < observation.height and 0 <= col < observation.width


def estimate_geometry(
    observation: Observation,
    *,
    target: str | None = None,
    pixel: tuple[int, int] | None = None,
    quantities: tuple[Quantity, ...] = ("center", "extent"),
    grounder: Grounder | None = None,
    segmenter: Segmenter | None = None,
    config: GeometryToolConfig | None = None,
) -> dict[str, Any]:
    """Localize one target in a synchronized observation.

    Either ``pixel`` or ``target`` must be supplied. Without a segmenter, a
    deterministic depth-and-color region around the point supplies the mask.
    """
    config = config or GeometryToolConfig()
    unknown = [quantity for quantity in quantities if quantity not in _QUANTITIES]
    if unknown:
        return _error(
            "error",
            "invalid_quantity",
            f"unsupported quantities: {unknown}",
            allowed=list(_QUANTITIES),
        )
    if pixel is None and not (target and target.strip()):
        return _error(
            "error",
            "missing_target",
            "provide a target description or a [row,col] pixel",
        )

    pixel_rc: tuple[int, int] | None = None
    grounding = "pixel"
    if pixel is not None:
        pixel_rc = (int(pixel[0]), int(pixel[1]))
        if not _pixel_in_bounds(pixel_rc, observation):
            return _error(
                "error",
                "pixel_out_of_bounds",
                "the pixel is outside the selected view",
                pixel_rc=list(pixel_rc),
                image_shape=list(observation.image_shape),
                view=observation.view,
            )
    else:
        if grounder is None:
            return _error(
                "error",
                "grounding_unavailable",
                "this runtime has no grounder; provide a [row,col] pixel",
                view=observation.view,
                step=observation.step,
            )
        grounding = "query"
        selected = grounder.ground(observation.rgb, str(target))
        if selected is None:
            return _error(
                "error",
                "target_not_found",
                "the grounder did not find the described target",
                target=target,
                view=observation.view,
                step=observation.step,
            )
        pixel_rc = (int(selected[0]), int(selected[1]))
        if not _pixel_in_bounds(pixel_rc, observation):
            return _error(
                "error",
                "pixel_out_of_bounds",
                "the grounder selected a pixel outside the view",
                pixel_rc=list(pixel_rc),
                image_shape=list(observation.image_shape),
                view=observation.view,
            )

    try:
        world_xyz = observation_world_xyz(
            {
                "image_shape": observation.image_shape,
                "world_xyz": observation.world_xyz,
                "depth": observation.depth,
                "intrinsics": observation.intrinsics,
                "world_from_camera": observation.world_from_camera,
                "camera_convention": observation.camera_convention,
            }
        )
    except ValueError as exc:
        return _error(
            "need_observation",
            "missing_geometry",
            str(exc),
            view=observation.view,
            step=observation.step,
            hint=(
                "render a state with depth and camera calibration; "
                "this view has neither a world map nor calibrated depth"
            ),
        )
    back_projection = (
        "persisted_world_xyz"
        if observation.world_xyz is not None
        and observation.world_xyz.shape[:2] == observation.image_shape
        else "depth_and_calibration"
    )

    segmentation = "injected"
    mask: np.ndarray | None = None
    if segmenter is not None:
        try:
            mask = segmenter.segment(observation.rgb, point=pixel_rc, query=target)
        except Exception as exc:
            return _error(
                "need_observation",
                "segmentation_failed",
                f"segmentation service failed: {type(exc).__name__}: {exc}",
                pixel_rc=list(pixel_rc),
                view=observation.view,
            )
        if mask is None:
            return _error(
                "error",
                "target_not_segmented",
                "segmentation found no mask for the selected target",
                pixel_rc=list(pixel_rc),
                view=observation.view,
                step=observation.step,
            )
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != observation.image_shape:
            return _error(
                "error",
                "mask_shape",
                "the segmenter returned a mask for a different image",
                mask_shape=list(mask.shape),
                image_shape=list(observation.image_shape),
            )
        if not mask.any():
            return _error(
                "error",
                "target_not_segmented",
                "segmentation returned an empty mask for the selected target",
                pixel_rc=list(pixel_rc),
                view=observation.view,
                step=observation.step,
            )
    else:
        segmentation = "depth_region"
        if observation.depth is None:
            return _error(
                "need_observation",
                "missing_depth",
                "this runtime has no segmenter and the view has no depth",
                view=observation.view,
                step=observation.step,
            )
        try:
            mask = depth_region_mask(
                observation.depth,
                observation.rgb,
                pixel_rc,
                config=config.quality,
            )
        except ValueError as exc:
            return _error(
                "error",
                "invalid_mask",
                str(exc),
                pixel_rc=list(pixel_rc),
                view=observation.view,
            )
    assert mask is not None

    try:
        fit = fit_mask(world_xyz, mask, config=config.quality)
    except ValueError as exc:
        return _error(
            "need_observation",
            "insufficient_depth",
            str(exc),
            pixel_rc=list(pixel_rc),
            view=observation.view,
            step=observation.step,
            hint="render again with the target inside the depth sensor's range",
        )

    refs = [
        observation.source_ref(),
        f"pixel_rc={list(pixel_rc)}",
        f"segmentation={segmentation}",
        f"back_projection={back_projection}",
    ]
    fields: dict[str, Any] = {}
    if "center" in quantities:
        fields["center"] = _field(
            fit.center.tolist(),
            unit="metre",
            definition="world-frame median of mask points",
            evidence="measured",
            refs=refs,
        )
    if "extent" in quantities:
        fields["extent"] = _field(
            fit.extent.tolist(),
            unit="metre",
            definition="world-frame axis-aligned range of mask points",
            evidence="measured",
            refs=refs,
        )
    if "z_range" in quantities:
        fields["z_range"] = _field(
            fit.z_range.tolist(),
            unit="metre",
            definition="world-frame z minimum and maximum of mask points",
            evidence="measured",
            refs=refs,
        )
    if "orientation" in quantities:
        if fit.yaw_rad is None:
            fields["orientation"] = _field(
                None,
                unit="radian",
                definition="yaw of the dominant horizontal principal axis",
                evidence="unknown",
                refs=refs,
            )
        else:
            fields["orientation"] = _field(
                {"yaw_rad": fit.yaw_rad},
                unit="radian",
                definition="yaw of the dominant horizontal principal axis",
                evidence="inferred",
                refs=refs,
            )

    status = "usable"
    if not fit.accepted:
        status = "partial"
    elif fit.warnings:
        status = "warning"
    return {
        "status": status,
        **fields,
        "pixel_rc": list(pixel_rc),
        "view": observation.view,
        "step": observation.step,
        "fit_accepted": fit.accepted,
        "method": {
            "grounding": grounding,
            "segmentation": segmentation,
            "back_projection": back_projection,
        },
        "quality": {
            "point_count": fit.point_count,
            "mask_pixels": fit.mask_pixels,
            "depth_coverage": fit.coverage,
            "outlier_fraction": fit.outlier_fraction,
        },
        "warnings": list(fit.warnings),
        "source_refs": refs,
    }


@tool(readonly=True, exclude=("provider", "grounder", "segmenter", "config"))
def geometry(
    *,
    provider: ObservationProvider,
    grounder: Grounder | None,
    segmenter: Segmenter | None,
    config: GeometryToolConfig,
    target: str | None = None,
    pixel: Annotated[list[int], Field(min_length=2, max_length=2)] | None = None,
    view: str | None = None,
    step: int | None = None,
    quantities: Annotated[list[Quantity], Field(min_length=1, max_length=4)]
    | None = None,
) -> ToolResult:
    """Localize one visible target from the current or a recorded camera view. Returns a world-frame center and axis-aligned extent with quality flags. Give a natural-language target when the runtime can ground it, or a [row,col] pixel measured on the selected view. Read-only; does not move the robot.

    Args:
        target: Natural-language target, e.g. 'the red block on the left'.
        pixel: [row, col] chosen on the selected view; skips grounding.
        view: Camera view; omit for the default view.
        step: Recorded step; -1 = latest.
        quantities: Requested measurements; defaults to center and extent.
    """
    try:
        observation = provider.observe(
            view=view,
            step=-1 if step is None else int(step),
        )
    except ObservationError as exc:
        return ToolResult(
            data=_error(
                "need_observation",
                exc.code,
                exc.message,
                **exc.details,
                hint="inspect available views and render a fresh observation",
            )
        )
    requested = tuple(quantities or config.default_quantities)
    payload = estimate_geometry(
        observation,
        target=target,
        pixel=None if pixel is None else (int(pixel[0]), int(pixel[1])),
        quantities=requested,
        grounder=grounder,
        segmenter=segmenter,
        config=config,
    )
    return ToolResult(data=payload)


def _pixel_only_arguments(schema: type[BaseModel]) -> type[BaseModel]:
    """Return the argument model for a host without a grounding service.

    ``target`` disappears from the schema, and ``pixel`` becomes a required
    non-null list. ``extra="forbid"`` makes a described target a call-time
    validation error instead of a silently ignored keyword.
    """
    fields: dict[str, Any] = {}
    for name, info in schema.model_fields.items():
        if name == "target":
            continue
        if name == "pixel":
            fields[name] = (
                Annotated[list[int], Field(min_length=2, max_length=2)],
                Field(..., description=info.description),
            )
            continue
        fields[name] = (info.annotation, info)
    return create_model(
        f"{schema.__name__}NoGrounding",
        __module__=schema.__module__,
        __config__=ConfigDict(extra="forbid", allow_inf_nan=False),
        **fields,
    )


class GeometryTools(ToolFamily):
    """Publish ``geometry`` when the host has calibrated depth views."""

    name = "geometry"

    def __init__(
        self,
        *,
        provider: ObservationProvider,
        grounder: Grounder | None = None,
        segmenter: Segmenter | None = None,
        config: GeometryToolConfig | None = None,
    ) -> None:
        self._provider = provider
        self._grounder = grounder
        self._segmenter = segmenter
        self._config = config or GeometryToolConfig()

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        if capabilities is not None and not (
            capabilities.has_depth() and capabilities.has_calibration()
        ):
            return ()
        declaration = geometry.with_handler(
            partial(
                geometry,
                provider=self._provider,
                grounder=self._grounder,
                segmenter=self._segmenter,
                config=self._config,
            )
        )
        if capabilities is not None and not capabilities.grounding:
            schema = declaration.input_schema
            schema["properties"].pop("target", None)
            schema["properties"]["pixel"] = {
                **schema["properties"]["pixel"],
                "type": "array",
            }
            schema["required"] = ["pixel"]
            declaration = replace(
                declaration,
                description=(
                    "Localize one visible target from the current or a recorded "
                    "camera view. This host has no grounding service, so pass a "
                    "[row,col] pixel measured on the selected view. Returns a "
                    "world-frame center and axis-aligned extent with quality "
                    "flags. Read-only; does not move the robot."
                ),
                args_schema=_pixel_only_arguments(declaration.args_schema),
                _input_schema=schema,
            )
        return (declaration,)


__all__ = [
    "GeometryToolConfig",
    "GeometryTools",
    "estimate_geometry",
    "geometry",
]
