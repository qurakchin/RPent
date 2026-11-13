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

The reference is a second renderer with a different construction from the
corpus renderer: it intersects each pixel ray with the three camera-facing box
faces, clips each intersection to that face's rectangle, and keeps the nearest
visible face after table occlusion. The corpus renderer instead intersects the
ray with the box as a whole through the slab method. Both read the same stored
scene parameters; neither reads the other's output, and the reference never
consumes tool output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


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
            "definition": ("exact visible surface, camera-facing face rasterization"),
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


def _camera_directions(camera: dict[str, Any], rotation: np.ndarray) -> np.ndarray:
    """Return one world-space ray direction per pixel."""
    height, width = (int(value) for value in camera["image_shape"])
    focal = float(camera["focal"])
    centre_x, centre_y = (width - 1) / 2.0, (height - 1) / 2.0
    rows, cols = np.mgrid[0:height, 0:width]
    local = np.stack(
        [
            (cols - centre_x) / focal,
            (rows - centre_y) / focal,
            np.ones_like(cols, dtype=np.float64),
        ],
        axis=-1,
    )
    return local @ rotation.T


def _face_distance(
    origin: np.ndarray,
    directions: np.ndarray,
    center: np.ndarray,
    half: np.ndarray,
    axis: int,
) -> np.ndarray:
    """Return the ray distance to one camera-facing box face.

    The camera lies on one side of ``center[axis]``, so that side's face is the
    one the ray enters the box through. The intersection must also fall inside
    the face rectangle on the other two axes; anything else is a miss.
    """
    step = half[axis] if origin[axis] >= center[axis] else -half[axis]
    plane = center[axis] + step
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = (plane - origin[axis]) / directions[..., axis]
        points = origin + distance[..., None] * directions
    inside = np.isfinite(distance) & (distance > 0.0)
    for other in range(3):
        if other == axis:
            continue
        inside &= (points[..., other] >= center[other] - half[other]) & (
            points[..., other] <= center[other] + half[other]
        )
    return np.where(inside, distance, np.inf)


def _box_distance(
    origin: np.ndarray,
    directions: np.ndarray,
    center: np.ndarray,
    half: np.ndarray,
) -> np.ndarray:
    """Return the nearest camera-facing face hit along each ray."""
    nearest = np.full(directions.shape[:-1], np.inf)
    for axis in range(3):
        nearest = np.minimum(
            nearest,
            _face_distance(origin, directions, center, half, axis),
        )
    return nearest


def _table_distance(
    origin: np.ndarray,
    directions: np.ndarray,
    table: dict[str, Any],
) -> np.ndarray:
    """Return the distance to the table plane inside its rectangle."""
    plane = float(table["height"])
    bounds = table["bounds"]
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = (plane - origin[2]) / directions[..., 2]
        points = origin + distance[..., None] * directions
    inside = (
        np.isfinite(distance)
        & (distance > 0.0)
        & (points[..., 0] >= bounds[0][0])
        & (points[..., 0] <= bounds[0][1])
        & (points[..., 1] >= bounds[1][0])
        & (points[..., 1] <= bounds[1][1])
    )
    return np.where(inside, distance, np.inf)


def visible_surface(case: dict[str, Any]) -> np.ndarray:
    """Return exact world points for the visible box surface."""
    camera = case["camera"]
    origin, rotation = _camera_frame(camera["position"], camera["target"])
    directions = _camera_directions(camera, rotation)
    center = np.asarray(case["box"]["center"], dtype=np.float64)
    half = np.asarray(case["box"]["size"], dtype=np.float64) / 2.0
    box = _box_distance(origin, directions, center, half)
    table = _table_distance(origin, directions, case["table"])
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
