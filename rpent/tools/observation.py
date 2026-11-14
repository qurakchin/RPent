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

"""Observation, grounding, and segmentation contracts for spatial tools.

Tool packages depend on these protocols instead of on a robot integration.
The host supplies an observation provider and, when its runtime exposes them,
grounding and segmentation adapters.

Pixel coordinates use ``[row, col]`` throughout. Camera extrinsics follow the
declared convention: ``opencv`` cameras look down +Z, while ``opengl`` cameras
look down -Z.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

import numpy as np


class ObservationError(Exception):
    """An observation could not be supplied for the requested view or step."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        """Return the structured error payload used by tools."""
        return {"code": self.code, "message": self.message, **self.details}


@dataclass(frozen=True)
class Observation:
    """One synchronized camera observation in world coordinates.

    ``world_xyz`` is authoritative when supplied by the host. Otherwise depth,
    intrinsics, and ``world_from_camera`` describe the same mapping and the
    tool back-projects on demand.
    """

    view: str
    step: int | None
    image_shape: tuple[int, int]
    rgb: np.ndarray
    depth: np.ndarray | None = None
    world_xyz: np.ndarray | None = None
    intrinsics: np.ndarray | None = None
    world_from_camera: np.ndarray | None = None
    camera_convention: str = "opencv"
    depth_unit: str = "metre"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def height(self) -> int:
        return self.image_shape[0]

    @property
    def width(self) -> int:
        return self.image_shape[1]

    def source_ref(self) -> str:
        """Return a stable reference to this observation for result provenance."""
        return f"view={self.view}@step{self.step}"


class ObservationProvider(Protocol):
    """Supply the most recent observation, or one recorded step."""

    def views(self) -> Sequence[str]:
        """Return the views available in the current state."""

    def default_view(self) -> str | None:
        """Return the view used when a caller omits one."""

    def observe(self, *, view: str | None = None, step: int | None = None) -> Observation:
        """Load one observation or raise :class:`ObservationError`."""


class Grounder(Protocol):
    """Select one visible point for a natural-language target."""

    def ground(self, rgb: np.ndarray, query: str) -> tuple[int, int] | None:
        """Return ``[row, col]`` in the supplied image, or None if absent."""


class Segmenter(Protocol):
    """Produce a boolean mask around a point or from a text prompt."""

    def segment(
        self,
        rgb: np.ndarray,
        *,
        point: tuple[int, int] | None = None,
        query: str | None = None,
    ) -> np.ndarray | None:
        """Return an ``[H,W]`` boolean mask, or None if nothing was found."""


__all__ = [
    "Grounder",
    "Observation",
    "ObservationError",
    "ObservationProvider",
    "Segmenter",
]
