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

"""Replay the geometry tool over the frozen synthetic corpus.

The masks are frozen inputs: replay never calls a grounding or segmentation
model. The fallback mode deliberately omits the mask to exercise the built-in
depth-region segmenter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from rpent.tools.observation import Observation
from toolkits.geometry.core import GeometryConfig
from toolkits.geometry.evaluation.corpus import render_case
from toolkits.geometry.evaluation.references import reference_from_render
from toolkits.geometry.tool import GeometryToolConfig, estimate_geometry


@dataclass(frozen=True)
class FrozenMaskSegmenter:
    """Return the corpus mask unchanged, standing in for a real segmenter."""

    mask: np.ndarray

    def segment(
        self,
        rgb: np.ndarray,
        *,
        point: tuple[int, int] | None = None,
        query: str | None = None,
    ) -> np.ndarray | None:
        del rgb, point, query
        return self.mask


def _observation(rendered: Any) -> Observation:
    return Observation(
        view="synthetic",
        step=int(rendered.case["index"]),
        image_shape=rendered.rgb.shape[:2],
        rgb=rendered.rgb,
        depth=rendered.depth,
        intrinsics=rendered.intrinsics,
        world_from_camera=rendered.world_from_camera,
        camera_convention="opencv",
        depth_unit="metre",
        metadata={"corpus": "synthetic-analytic", "case_id": rendered.case["case_id"]},
    )


def replay_case(
    case: dict[str, Any],
    *,
    quality: GeometryConfig | None = None,
    use_frozen_mask: bool = True,
) -> dict[str, Any]:
    """Run one case and compare it with its analytic reference."""
    rendered = render_case(case)
    reference = reference_from_render(rendered).as_dict()
    config = GeometryToolConfig(quality=quality or GeometryConfig())
    payload = estimate_geometry(
        _observation(rendered),
        pixel=tuple(case["pixel"]),
        quantities=tuple(case["quantities"]),
        segmenter=FrozenMaskSegmenter(rendered.mask) if use_frozen_mask else None,
        config=config,
    )
    status = payload.get("status", "missing")
    if payload.get("error"):
        status = "error"
    center_error = extent_error = None
    if status != "error" and "center" in payload:
        center_error = float(
            np.linalg.norm(
                np.asarray(payload["center"]["value"], dtype=np.float64)
                - np.asarray(reference["center"], dtype=np.float64)
            )
        )
        extent_error = float(
            np.linalg.norm(
                np.asarray(payload["extent"]["value"], dtype=np.float64)
                - np.asarray(reference["extent"], dtype=np.float64)
            )
        )
    return {
        "case_id": case["case_id"],
        "index": case["index"],
        "group": case["group"],
        "expect_visible": case["expect_visible"],
        "noise": case.get("depth_noise_rel", 0.0),
        "status": status,
        "fit_accepted": payload.get("fit_accepted"),
        "warnings": [
            str(warning.get("code")) for warning in payload.get("warnings", [])
        ],
        "center_error_m": center_error,
        "extent_error_m": extent_error,
        "reference": reference,
        "payload": payload,
    }


def replay(
    cases: list[dict[str, Any]],
    *,
    quality: GeometryConfig | None = None,
    use_frozen_mask: bool = True,
) -> list[dict[str, Any]]:
    """Replay every case in order."""
    return [
        replay_case(case, quality=quality, use_frozen_mask=use_frozen_mask)
        for case in cases
    ]


__all__ = ["FrozenMaskSegmenter", "replay", "replay_case"]
