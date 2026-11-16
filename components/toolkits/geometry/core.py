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

"""Analytic geometry for masked regions of one calibrated RGB-D observation.

This module has no RPent imports: it can be evaluated, replayed, and reused
without constructing a toolkit or a robot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

CONVENTIONS = {"opencv", "opengl"}


@dataclass(frozen=True)
class GeometryConfig:
    """Quality thresholds for one geometry estimate.

    ``max_extent_m`` rejects masks that leaked into the workspace; the other
    thresholds decide whether the measured point cloud supports a usable fit.
    """

    max_extent_m: float = 2.0
    min_points: int = 40
    min_coverage: float = 0.15
    outlier_margin_fraction: float = 0.25
    outlier_margin_m: float = 0.02
    depth_jump_rel: float = 0.06
    depth_noise_floor_m: float = 0.004
    color_tolerance: float = 45.0
    min_depth_m: float = 0.02
    max_depth_m: float = 10.0


@dataclass(frozen=True)
class CloudFit:
    """Robust world-frame fit of the finite points inside a mask."""

    center: np.ndarray
    extent: np.ndarray
    z_range: np.ndarray
    point_count: int
    mask_pixels: int
    coverage: float
    outlier_fraction: float
    yaw_rad: float | None
    warnings: tuple[dict[str, str], ...] = ()
    accepted: bool = True


def back_project(
    depth: np.ndarray,
    intrinsics: np.ndarray,
    world_from_camera: np.ndarray,
    *,
    convention: str = "opencv",
) -> np.ndarray:
    """Map a metric depth image to world coordinates with shape ``[H,W,3]``.

    Args:
        depth: Metric depth with shape ``[H,W]``; non-positive values are invalid.
        intrinsics: ``3x3`` camera matrix.
        world_from_camera: ``4x4`` camera-to-world transform.
        convention: ``opencv`` (camera looks down +Z) or ``opengl`` (down -Z).

    Returns:
        World points with invalid pixels set to NaN.
    """
    if convention not in CONVENTIONS:
        raise ValueError(f"unsupported camera convention: {convention!r}")
    depth = np.asarray(depth, dtype=np.float64)
    intrinsics = np.asarray(intrinsics, dtype=np.float64)
    world_from_camera = np.asarray(world_from_camera, dtype=np.float64)
    if depth.ndim != 2:
        raise ValueError(f"depth must have shape [H,W], got {depth.shape}")
    if intrinsics.shape != (3, 3):
        raise ValueError("intrinsics must have shape [3,3]")
    if world_from_camera.shape != (4, 4):
        raise ValueError("world_from_camera must have shape [4,4]")
    if not np.isfinite(intrinsics).all() or not np.isfinite(world_from_camera).all():
        raise ValueError("camera calibration must contain only finite values")
    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    if fx <= 0 or fy <= 0:
        raise ValueError("camera focal lengths must be positive")

    height, width = depth.shape
    rows, cols = np.mgrid[0:height, 0:width]
    valid = np.isfinite(depth) & (depth > 0)
    z = np.where(valid, depth, np.nan)
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]
    if convention == "opencv":
        camera_x = (cols - cx) * z / fx
        camera_y = (rows - cy) * z / fy
        camera_z = z
    else:
        camera_x = (cols - cx) * z / fx
        camera_y = -(rows - cy) * z / fy
        camera_z = -z
    camera_points = np.stack([camera_x, camera_y, camera_z], axis=-1)
    rotation = world_from_camera[:3, :3]
    translation = world_from_camera[:3, 3]
    world = camera_points @ rotation.T + translation
    world[~valid] = np.nan
    return world


def depth_region_mask(
    depth: np.ndarray,
    rgb: np.ndarray,
    pixel: tuple[int, int],
    *,
    config: GeometryConfig | None = None,
) -> np.ndarray:
    """Grow a mask from ``pixel`` over locally continuous depth and color.

    The fallback segmenter is deterministic and model-free. It stops at depth
    discontinuities and color boundaries; a mask that still leaks is rejected
    downstream by the extent check.
    """
    config = config or GeometryConfig()
    depth = np.asarray(depth, dtype=np.float64)
    rgb = np.asarray(rgb)
    if depth.ndim != 2:
        raise ValueError(f"depth must have shape [H,W], got {depth.shape}")
    row, col = int(pixel[0]), int(pixel[1])
    height, width = depth.shape
    if not (0 <= row < height and 0 <= col < width):
        raise ValueError(f"pixel {[row, col]} is outside a {height}x{width} image")
    seed_depth = depth[row, col]
    if not np.isfinite(seed_depth) or seed_depth <= 0:
        raise ValueError("the selected pixel has no finite metric depth")

    mask = np.zeros((height, width), dtype=bool)
    mask[row, col] = True
    stack = [(row, col)]
    seed_color = rgb[row, col].astype(np.float64)
    while stack:
        current_row, current_col = stack.pop()
        current_depth = depth[current_row, current_col]
        for next_row, next_col in (
            (current_row - 1, current_col),
            (current_row + 1, current_col),
            (current_row, current_col - 1),
            (current_row, current_col + 1),
        ):
            if not (0 <= next_row < height and 0 <= next_col < width):
                continue
            if mask[next_row, next_col]:
                continue
            neighbor_depth = depth[next_row, next_col]
            if not np.isfinite(neighbor_depth) or neighbor_depth <= 0:
                continue
            tolerance = max(
                config.depth_jump_rel * abs(current_depth),
                config.depth_noise_floor_m,
            )
            if abs(neighbor_depth - current_depth) > tolerance:
                continue
            color = rgb[next_row, next_col].astype(np.float64)
            if np.linalg.norm(color - seed_color) > config.color_tolerance:
                continue
            mask[next_row, next_col] = True
            stack.append((next_row, next_col))
    return mask


def fit_mask(
    world_xyz: np.ndarray,
    mask: np.ndarray,
    *,
    config: GeometryConfig | None = None,
) -> CloudFit:
    """Fit center, axis-aligned extent, and yaw to the mask's world points.

    The median center and the core-plus-margin trim make a few depth spikes
    harmless without discarding a visible face. Extent is the world-frame
    axis-aligned range, which matches a box-like target and is reported with
    that definition rather than as true dimensions.
    """
    config = config or GeometryConfig()
    world_xyz = np.asarray(world_xyz, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if world_xyz.ndim != 3 or world_xyz.shape[2] != 3:
        raise ValueError(f"world_xyz must have shape [H,W,3], got {world_xyz.shape}")
    if mask.shape != world_xyz.shape[:2]:
        raise ValueError(
            f"mask shape {mask.shape} does not match world_xyz {world_xyz.shape[:2]}"
        )
    mask_pixels = int(mask.sum())
    if mask_pixels == 0:
        raise ValueError("mask is empty")
    points = world_xyz[mask]
    points = points[np.isfinite(points).all(axis=1)]
    finite_count = len(points)
    if not finite_count:
        raise ValueError("mask has no finite world points")

    center = np.median(points, axis=0)
    # Trim only implausible outliers. A box seen from one side has a bimodal
    # per-axis distribution (top face plus side face), so MAD or IQR trimming
    # would discard real geometry. Keep the 2-98% core plus a margin; this
    # removes sparse depth spikes while preserving every visible face.
    lower, upper = np.percentile(points, [2, 98], axis=0)
    margin = np.maximum(
        config.outlier_margin_m,
        config.outlier_margin_fraction * (upper - lower),
    )
    kept = points[
        np.all((points >= lower - margin) & (points <= upper + margin), axis=1)
    ]
    if len(kept) >= config.min_points:
        points = kept
    outlier_fraction = 1.0 - len(points) / finite_count
    center = np.median(points, axis=0)

    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    extent = maximum - minimum
    z_range = np.asarray([minimum[2], maximum[2]])
    coverage = finite_count / mask_pixels
    yaw = _principal_yaw(points)

    warnings: list[dict[str, str]] = []
    accepted = True
    if len(points) < config.min_points:
        accepted = False
        warnings.append(
            {
                "code": "small_mask",
                "message": f"{len(points)} finite points is below {config.min_points}",
            }
        )
    if coverage < config.min_coverage:
        accepted = False
        warnings.append(
            {
                "code": "sparse_depth",
                "message": (
                    f"{coverage:.2f} of mask pixels have metric depth, below "
                    f"{config.min_coverage:.2f}"
                ),
            }
        )
    if float(extent.max()) > config.max_extent_m:
        accepted = False
        warnings.append(
            {
                "code": "extent_too_large",
                "message": (
                    f"{float(extent.max()):.2f} m exceeds {config.max_extent_m:.2f} m; "
                    "the mask may have leaked into the workspace"
                ),
            }
        )
    if float(center[2]) < config.min_depth_m:
        accepted = False
        warnings.append(
            {
                "code": "depth_too_close",
                "message": f"median depth {float(center[2]):.3f} m is implausible",
            }
        )
    if outlier_fraction > 0.02:
        warnings.append(
            {
                "code": "depth_outliers",
                "message": f"{outlier_fraction:.1%} of mask points were outliers",
            }
        )
    return CloudFit(
        center=center,
        extent=extent,
        z_range=z_range,
        point_count=len(points),
        mask_pixels=mask_pixels,
        coverage=coverage,
        outlier_fraction=outlier_fraction,
        yaw_rad=yaw,
        warnings=tuple(warnings),
        accepted=accepted,
    )


def _principal_yaw(points: np.ndarray) -> float | None:
    """Yaw of the dominant horizontal principal axis, if one is meaningful."""
    centered = points - points.mean(axis=0)
    if len(centered) < 3:
        return None
    covariance = np.cov(centered, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    horizontal = float(np.hypot(axis[0], axis[1]))
    if horizontal < 0.3:
        return None
    return float(np.arctan2(axis[1], axis[0]))


def observation_world_xyz(observation: Mapping[str, Any]) -> np.ndarray:
    """Resolve world points from a persisted map or from calibrated depth.

    A host-supplied ``world_xyz`` is used only when it matches the image shape;
    otherwise depth plus calibration is authoritative.
    """
    image_shape = tuple(int(value) for value in observation["image_shape"])
    world = observation.get("world_xyz")
    if isinstance(world, np.ndarray) and world.shape[:2] == image_shape:
        if world.ndim == 3 and world.shape[2] == 3:
            return np.asarray(world, dtype=np.float64)
    depth = observation.get("depth")
    intrinsics = observation.get("intrinsics")
    world_from_camera = observation.get("world_from_camera")
    if depth is None or intrinsics is None or world_from_camera is None:
        raise ValueError(
            "observation needs world_xyz or depth plus intrinsics and camera pose"
        )
    return back_project(
        depth,
        intrinsics,
        world_from_camera,
        convention=str(observation.get("camera_convention", "opencv")),
    )


__all__ = [
    "CloudFit",
    "GeometryConfig",
    "back_project",
    "depth_region_mask",
    "fit_mask",
    "observation_world_xyz",
]
