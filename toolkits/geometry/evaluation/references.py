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

"""Independent analytic references for one synthetic case.

The reference re-derives the visible surface from the stored scene parameters
with its own ray casting. It does not read the corpus renderer's depth, mask,
or world coordinates, and it never consumes tool output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from toolkits.geometry.evaluation.corpus import (
    FOCAL,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    TABLE_BOUNDS,
)


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
            "definition": "exact visible surface, independently ray-cast",
        }


def _camera_frame(
    position: list[float], target: list[float]
) -> tuple[np.ndarray, np.ndarray]:
    origin = np.asarray(position, dtype=np.float64)
    forward = np.asarray(target, dtype=np.float64) - origin
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray([0.0, 0.0, 1.0]))
    length = np.linalg.norm(right)
    if length < 1e-8:
        right = np.asarray([1.0, 0.0, 0.0])
    else:
        right /= length
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward], axis=1)
    return origin, rotation


def _ray_directions() -> np.ndarray:
    columns, rows = np.meshgrid(
        np.arange(IMAGE_WIDTH, dtype=np.float64),
        np.arange(IMAGE_HEIGHT, dtype=np.float64),
    )
    cx, cy = (IMAGE_WIDTH - 1) / 2.0, (IMAGE_HEIGHT - 1) / 2.0
    return np.stack(
        [(columns - cx) / FOCAL, (rows - cy) / FOCAL, np.ones_like(columns)],
        axis=-1,
    )


def _box_distance(
    origin: np.ndarray,
    directions: np.ndarray,
    minimum: np.ndarray,
    maximum: np.ndarray,
) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        near = np.max(
            np.minimum(
                (minimum - origin) / directions, (maximum - origin) / directions
            ),
            axis=-1,
        )
        far = np.min(
            np.maximum(
                (minimum - origin) / directions, (maximum - origin) / directions
            ),
            axis=-1,
        )
    hit = (far >= np.maximum(near, 0.0)) & (near > 0.0)
    return np.where(hit, near, np.inf)


def _table_distance(origin: np.ndarray, directions: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = -origin[2] / directions[..., 2]
    points = origin + distance[..., None] * directions
    inside = (
        (distance > 0)
        & (points[..., 0] >= TABLE_BOUNDS[0][0])
        & (points[..., 0] <= TABLE_BOUNDS[0][1])
        & (points[..., 1] >= TABLE_BOUNDS[1][0])
        & (points[..., 1] <= TABLE_BOUNDS[1][1])
        & np.isfinite(distance)
    )
    return np.where(inside, distance, np.inf)


def visible_surface(case: dict[str, Any]) -> np.ndarray:
    """Return exact world points for the visible box surface."""
    camera = case["camera"]
    origin, rotation = _camera_frame(camera["position"], camera["target"])
    directions = _ray_directions() @ rotation.T
    center = np.asarray(case["box"]["center"], dtype=np.float64)
    size = np.asarray(case["box"]["size"], dtype=np.float64)
    minimum, maximum = center - size / 2.0, center + size / 2.0
    box = _box_distance(origin, directions, minimum, maximum)
    table = _table_distance(origin, directions)
    visible = np.isfinite(box) & (box <= table)
    return origin + box[visible, None] * directions[visible]


def reference_from_case(case: dict[str, Any]) -> Reference:
    """Compute the reference from stored parameters without the renderer."""
    points = visible_surface(case)
    if not len(points):
        raise ValueError("case has no exact visible surface")
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    return Reference(
        center=np.median(points, axis=0),
        extent=maximum - minimum,
        z_range=np.asarray([minimum[2], maximum[2]]),
        visible_points=len(points),
        box_center=np.asarray(case["box"]["center"], dtype=np.float64),
        box_size=np.asarray(case["box"]["size"], dtype=np.float64),
    )


__all__ = ["Reference", "reference_from_case", "visible_surface"]
