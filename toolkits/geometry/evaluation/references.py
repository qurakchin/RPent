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

"""Analytic references for one rendered case.

The reference is computed from the exact, unnoised visible surface before the
tool sees the observation. It shares no code path with segmentation, outlier
trimming, or the tool's noise handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from toolkits.geometry.evaluation.corpus import RenderedCase


@dataclass(frozen=True)
class Reference:
    """Observable surface reference plus the underlying object parameters."""

    center: np.ndarray
    extent: np.ndarray
    z_range: np.ndarray
    visible_points: int
    box_center: np.ndarray
    box_size: np.ndarray

    def as_dict(self) -> dict[str, Any]:
        return {
            "center": self.center.tolist(),
            "extent": self.extent.tolist(),
            "z_range": self.z_range.tolist(),
            "visible_points": self.visible_points,
            "box_center": self.box_center.tolist(),
            "box_size": self.box_size.tolist(),
            "definition": "exact visible surface, unnoised",
        }


def reference_from_render(rendered: RenderedCase) -> Reference:
    """Compute the reference directly from the analytic surface."""
    points = rendered.exact_world_xyz[rendered.exact_mask]
    points = points[np.isfinite(points).all(axis=1)]
    if not len(points):
        raise ValueError("rendered case has no exact visible points")
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    return Reference(
        center=np.median(points, axis=0),
        extent=maximum - minimum,
        z_range=np.asarray([minimum[2], maximum[2]]),
        visible_points=len(points),
        box_center=np.asarray(rendered.case["box"]["center"], dtype=np.float64),
        box_size=np.asarray(rendered.case["box"]["size"], dtype=np.float64),
    )


__all__ = ["Reference", "reference_from_render"]
