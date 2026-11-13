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

"""Deterministic synthetic-analytic RGB-D corpus.

The manifest stores scene parameters, not predictions. Rendering is a versioned
pure function of those parameters, so replay recomputes every input from
scratch. This is a CPU-only analytic corpus, not a real-platform accuracy
baseline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

CORPUS_VERSION = "synthetic-analytic-v2"
IMAGE_HEIGHT = 120
IMAGE_WIDTH = 160
FOCAL = 180.0
DEFAULT_SEED = 20260801
VISIBLE_CASES = 56
NOISY_CASES = 12
REJECTED_CASES = 12
TABLE_BOUNDS = ((-0.55, 0.55), (-0.45, 0.45))
TABLE_HEIGHT = 0.0


@dataclass(frozen=True)
class RenderedCase:
    """One frozen input plus the analytic surface used as the reference."""

    case: dict[str, Any]
    rgb: np.ndarray
    depth: np.ndarray
    intrinsics: np.ndarray
    world_from_camera: np.ndarray
    mask: np.ndarray
    exact_world_xyz: np.ndarray
    exact_mask: np.ndarray


def _camera_pose(
    position: list[float], target: list[float]
) -> tuple[np.ndarray, np.ndarray]:
    position_array = np.asarray(position, dtype=np.float64)
    forward = np.asarray(target, dtype=np.float64) - position_array
    forward /= np.linalg.norm(forward)
    world_up = np.asarray([0.0, 0.0, 1.0])
    right = np.cross(forward, world_up)
    norm = np.linalg.norm(right)
    if norm < 1e-8:
        right = np.asarray([1.0, 0.0, 0.0])
    else:
        right /= norm
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward], axis=1)
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = position_array
    return transform, position_array


def _intrinsics(camera: dict[str, Any]) -> np.ndarray:
    """Return the pinhole intrinsics stored with the case's camera."""
    height, width = (int(value) for value in camera["image_shape"])
    focal = float(camera["focal"])
    return np.asarray(
        [
            [focal, 0.0, (width - 1) / 2.0],
            [0.0, focal, (height - 1) / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _local_directions(camera: dict[str, Any]) -> np.ndarray:
    height, width = (int(value) for value in camera["image_shape"])
    rows, cols = np.mgrid[0:height, 0:width]
    intrinsics = _intrinsics(camera)
    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]
    return np.stack(
        [(cols - cx) / fx, (rows - cy) / fy, np.ones_like(cols, dtype=np.float64)],
        axis=-1,
    )


def _ray_box(
    origin: np.ndarray,
    directions: np.ndarray,
    minimum: np.ndarray,
    maximum: np.ndarray,
) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        first = (minimum - origin) / directions
        second = (maximum - origin) / directions
    near = np.max(np.minimum(first, second), axis=-1)
    far = np.min(np.maximum(first, second), axis=-1)
    hit = (far >= np.maximum(near, 0.0)) & (near > 0.0)
    return np.where(hit, near, np.inf)


def _ray_table(
    origin: np.ndarray,
    directions: np.ndarray,
    table: dict[str, Any],
) -> np.ndarray:
    height = float(table["height"])
    bounds = table["bounds"]
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = (height - origin[2]) / directions[..., 2]
    points = origin + distance[..., None] * directions
    inside = (
        (distance > 0)
        & (points[..., 0] >= bounds[0][0])
        & (points[..., 0] <= bounds[0][1])
        & (points[..., 1] >= bounds[1][0])
        & (points[..., 1] <= bounds[1][1])
        & np.isfinite(distance)
    )
    return np.where(inside, distance, np.inf)


def render_case(case: dict[str, Any]) -> RenderedCase:
    """Render one case deterministically from its stored parameters."""
    camera = case["camera"]
    height, width = (int(value) for value in camera["image_shape"])
    world_from_camera, origin = _camera_pose(camera["position"], camera["target"])
    directions = _local_directions(camera) @ world_from_camera[:3, :3].T
    center = np.asarray(case["box"]["center"], dtype=np.float64)
    size = np.asarray(case["box"]["size"], dtype=np.float64)
    minimum = center - size / 2.0
    maximum = center + size / 2.0
    box_distance = _ray_box(origin, directions, minimum, maximum)
    table_distance = _ray_table(origin, directions, case["table"])
    nearest = np.minimum(box_distance, table_distance)
    box_hit = np.isfinite(box_distance) & (box_distance <= table_distance)
    table_hit = np.isfinite(table_distance) & ~box_hit
    visible = np.isfinite(nearest)

    depth = np.where(visible, nearest, 0.0)
    world = origin + depth[..., None] * directions
    world[~visible] = np.nan

    rgb = np.zeros((height, width, 3), dtype=np.float64)
    rows, cols = np.mgrid[0:height, 0:width]
    checker = (((rows // 8) + (cols // 8)) % 2) * 20.0
    rgb[table_hit] = np.stack(
        [95.0 + checker, 95.0 + checker, 100.0 + checker], axis=-1
    )[table_hit]
    box_color = np.asarray(case["box"]["color"], dtype=np.float64)
    shade = 0.75 + 0.25 * np.clip(1.0 - depth / 2.0, 0.0, 1.0)
    rgb[box_hit] = (box_color[None, :] * shade[..., None])[box_hit]
    rgb = np.clip(rgb, 0, 255)

    noise = float(case.get("depth_noise_rel", 0.0))
    mask = box_hit.copy()
    exact_world, exact_mask = world.copy(), mask
    if case.get("force_empty_mask"):
        mask = np.zeros_like(mask)
    if noise > 0:
        rng = np.random.default_rng([int(case["seed"]), int(case["index"])])
        jitter = rng.normal(0.0, noise, size=depth.shape)
        depth = np.where(depth > 0, depth * (1.0 + jitter), 0.0)
        rgb = np.clip(rgb + rng.normal(0.0, 2.0, size=rgb.shape), 0, 255)
    return RenderedCase(
        case=case,
        rgb=rgb.astype(np.uint8),
        depth=depth.astype(np.float64),
        intrinsics=_intrinsics(camera),
        world_from_camera=world_from_camera,
        mask=mask,
        exact_world_xyz=exact_world,
        exact_mask=exact_mask,
    )


def _project(
    point: np.ndarray,
    world_from_camera: np.ndarray,
    camera: dict[str, Any],
) -> tuple[float, float] | None:
    camera_point = world_from_camera[:3, :3].T @ (point - world_from_camera[:3, 3])
    if camera_point[2] <= 0:
        return None
    intrinsics = _intrinsics(camera)
    height, width = (int(value) for value in camera["image_shape"])
    column = intrinsics[0, 0] * camera_point[0] / camera_point[2] + intrinsics[0, 2]
    row = intrinsics[1, 1] * camera_point[1] / camera_point[2] + intrinsics[1, 2]
    if not (0 <= row < height and 0 <= column < width):
        return None
    return float(row), float(column)


def _pixel_on_mask(
    mask: np.ndarray, projected: tuple[float, float] | None
) -> list[int] | None:
    rows, cols = np.nonzero(mask)
    if not len(rows):
        return None
    if projected is not None:
        row, col = projected
        index = int(np.argmin((rows - row) ** 2 + (cols - col) ** 2))
        return [int(rows[index]), int(cols[index])]
    centre_row, centre_col = rows.mean(), cols.mean()
    index = int(np.argmin((rows - centre_row) ** 2 + (cols - centre_col) ** 2))
    return [int(rows[index]), int(cols[index])]


def _candidate(rng: np.random.Generator, index: int, noise: float) -> dict[str, Any]:
    center = np.asarray(
        [
            rng.uniform(-0.22, 0.22),
            rng.uniform(-0.16, 0.16),
            rng.uniform(0.025, 0.085),
        ]
    )
    size = np.asarray(
        [
            rng.uniform(0.045, 0.12),
            rng.uniform(0.045, 0.12),
            rng.uniform(0.035, 0.11),
        ]
    )
    position = [
        float(rng.uniform(0.62, 0.82)),
        float(rng.uniform(-0.18, 0.18)),
        float(rng.uniform(0.85, 1.15)),
    ]
    target = (center + rng.normal(0.0, 0.01, size=3)).tolist()
    color = rng.integers(40, 230, size=3).astype(float).tolist()
    return {
        "index": index,
        "seed": DEFAULT_SEED,
        "task": "box_localization",
        "group": "noisy" if noise > 0 else "clean",
        "depth_noise_rel": noise,
        "camera": {
            "position": position,
            "target": target,
            "image_shape": [IMAGE_HEIGHT, IMAGE_WIDTH],
            "focal": FOCAL,
        },
        "box": {"center": center.tolist(), "size": size.tolist(), "color": color},
        "table": {
            "height": TABLE_HEIGHT,
            "bounds": [list(bound) for bound in TABLE_BOUNDS],
        },
    }


def _finalize(case: dict[str, Any], rendered: RenderedCase) -> dict[str, Any]:
    visible = int(rendered.exact_mask.sum()) >= 300
    if visible:
        projected = _project(
            np.asarray(case["box"]["center"], dtype=np.float64),
            rendered.world_from_camera,
            case["camera"],
        )
        pixel = _pixel_on_mask(rendered.mask, projected)
    else:
        pixel = [5, 5]
    case = {
        **case,
        "case_id": f"synthetic_t{int(case['index']):03d}_s{DEFAULT_SEED}",
        "image_shape": list(case["camera"]["image_shape"]),
        "expect_visible": bool(visible),
        "pixel": pixel,
        "quantities": ["center", "extent"],
    }
    return case


def build_cases(
    *,
    seed: int = DEFAULT_SEED,
    visible: int = VISIBLE_CASES,
    noisy: int = NOISY_CASES,
    rejected: int = REJECTED_CASES,
) -> list[dict[str, Any]]:
    """Return the fixed corpus in deterministic order."""
    rng = np.random.default_rng(seed)
    cases: list[dict[str, Any]] = []
    index = 0
    while len(cases) < visible:
        candidate = _candidate(rng, index, 0.0)
        rendered = render_case(candidate)
        finalized = _finalize(candidate, rendered)
        index += 1
        if not finalized["expect_visible"]:
            continue
        cases.append(finalized)
    while len(cases) < visible + noisy:
        candidate = _candidate(rng, index, 0.01)
        rendered = render_case(candidate)
        finalized = _finalize(candidate, rendered)
        index += 1
        if not finalized["expect_visible"]:
            continue
        cases.append(finalized)
    while len(cases) < visible + noisy + rejected:
        candidate = _candidate(rng, index, 0.0)
        candidate["group"] = "rejected"
        candidate["force_empty_mask"] = True
        rendered = render_case(candidate)
        finalized = _finalize(candidate, rendered)
        finalized["expect_visible"] = False
        finalized["pixel"] = [5, 5]
        index += 1
        cases.append(finalized)
    return cases


def fingerprint(cases: list[dict[str, Any]]) -> str:
    """Return the content hash stored in the replay manifest."""
    payload = json.dumps(
        {"version": CORPUS_VERSION, "cases": cases},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_manifest(cases: list[dict[str, Any]], path: str) -> None:
    """Write the corpus manifest for a replay run."""
    from pathlib import Path

    Path(path).write_text(
        json.dumps(
            {
                "version": CORPUS_VERSION,
                "fingerprint": fingerprint(cases),
                "renderer": "toolkits.geometry.evaluation.corpus.render_case",
                "cases": cases,
            },
            indent=2,
        )
    )


__all__ = [
    "CORPUS_VERSION",
    "RenderedCase",
    "build_cases",
    "fingerprint",
    "render_case",
    "write_manifest",
]
