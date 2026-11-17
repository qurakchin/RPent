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

"""Pin each slice's depth projection to its camera convention and reference math.

The slices share :func:`toolkits.geometry.core.back_project`, but their camera
frames differ: LIBERO records OpenCV poses that look down +Z, while RoboDojo and
RoboTwin use USD/OpenGL poses that look down -Z with rows growing upward. Each
helper also drops pixels without a positive measurement. These tests state that
behavior independently of the implementation so a future edit cannot silently
change one slice's convention.
"""

from __future__ import annotations

import numpy as np
import pytest

from robots.libero import tools as libero_tools
from robots.robodojo import tools as robodojo_tools
from robots.robotwin.observation import world_from_depth as robotwin_world_from_depth

_INTRINSICS = np.array(
    [[2.0, 0.0, 1.0], [0.0, 3.0, 1.0], [0.0, 0.0, 1.0]],
)
_POSE = np.array(
    [
        [0.0, -1.0, 0.0, 3.0],
        [1.0, 0.0, 0.0, 4.0],
        [0.0, 0.0, 1.0, 5.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
)
_DEPTH = np.array(
    [
        [1.0, 2.0, 0.0],
        [0.5, -1.0, np.inf],
        [np.nan, 4.0, 6.0],
    ]
)


def _unmeasured(depth: np.ndarray) -> np.ndarray:
    return ~np.isfinite(depth) | (depth <= 0)


def _reference(
    depth: np.ndarray,
    *,
    convention: str,
    intrinsics: np.ndarray = _INTRINSICS,
    world_from_camera: np.ndarray = _POSE,
) -> np.ndarray:
    """Project depth with the documented per-slice camera axes."""
    depth = np.asarray(depth, dtype=np.float64)
    valid = ~_unmeasured(depth)
    z = np.where(valid, depth, np.nan)
    rows, cols = np.mgrid[0 : depth.shape[0], 0 : depth.shape[1]]
    x = (cols - intrinsics[0, 2]) * z / intrinsics[0, 0]
    y = (rows - intrinsics[1, 2]) * z / intrinsics[1, 1]
    if convention == "opencv":
        camera_points = np.stack([x, y, z], axis=-1)
    else:
        camera_points = np.stack([x, -y, -z], axis=-1)
    world = camera_points @ world_from_camera[:3, :3].T + world_from_camera[:3, 3]
    world[~valid] = np.nan
    return world


def test_libero_projection_uses_the_recorded_opencv_pose() -> None:
    camera_meta = {
        "intrinsic_K": _INTRINSICS,
        "extrinsic_cam2world": _POSE,
    }

    actual = libero_tools._world_from_depth(_DEPTH, camera_meta)

    np.testing.assert_allclose(
        actual, _reference(_DEPTH, convention="opencv"), equal_nan=True
    )
    # Pixel (0,0) with depth 1m sits left and above the principal point, and
    # OpenCV +Y grows downward, so the row term adds to y before rotation.
    np.testing.assert_allclose(actual[0, 0], [10 / 3, 3.5, 6.0])
    assert np.isnan(actual[_unmeasured(_DEPTH)]).all()


def test_robodojo_projection_uses_the_usd_camera_axes() -> None:
    actual = robodojo_tools._world_from_depth(_DEPTH, _INTRINSICS, _POSE)

    np.testing.assert_allclose(
        actual, _reference(_DEPTH, convention="opengl"), equal_nan=True
    )
    # The same pixel is above the principal point, so USD +Y adds downward.
    np.testing.assert_allclose(actual[0, 0], [8 / 3, 3.5, 4.0])
    assert actual.dtype == np.float32
    assert np.isnan(actual[_unmeasured(_DEPTH)]).all()


def test_robotwin_projection_uses_the_gl_camera_axes() -> None:
    camera_meta = {
        "intrinsic_K": _INTRINSICS,
        "cam2world_gl": _POSE,
        "height": _DEPTH.shape[0],
        "width": _DEPTH.shape[1],
    }

    actual = robotwin_world_from_depth(_DEPTH, camera_meta)

    np.testing.assert_allclose(
        actual, _reference(_DEPTH, convention="opengl"), equal_nan=True
    )
    np.testing.assert_allclose(actual[0, 0], [8 / 3, 3.5, 4.0])
    assert actual.dtype == np.float32
    assert np.isnan(actual[_unmeasured(_DEPTH)]).all()


def test_robotwin_projection_rejects_depth_that_contradicts_camera_metadata() -> None:
    camera_meta = {
        "intrinsic_K": _INTRINSICS,
        "cam2world_gl": _POSE,
        "height": 2,
        "width": 3,
    }

    with pytest.raises(ValueError, match="does not match camera metadata"):
        robotwin_world_from_depth(_DEPTH, camera_meta)
