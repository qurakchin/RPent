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

"""RoboTwin adapters for the geometry grounder and segmenter protocols.

The core tool families know the protocols, not the model clients. Keeping the
adapters in the slice means another robot can connect a different grounder or
segmenter without changing ``rpent/tools`` (a_global R8).
"""

from __future__ import annotations

from typing import Any

import numpy as np


class MolmoGrounder:
    """Adapt a Molmo RPC client to the geometry grounder protocol."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def ground(self, rgb: np.ndarray, query: str) -> tuple[int, int] | None:
        result = self._client.ground(rgb, query)
        if not result.found or result.point_xy is None:
            return None
        col, row = result.point_xy
        return int(round(row)), int(round(col))


class Sam3Segmenter:
    """Adapt a SAM3 RPC client to the geometry segmenter protocol."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def segment(
        self,
        rgb: np.ndarray,
        *,
        point: tuple[int, int] | None = None,
        query: str | None = None,
    ) -> np.ndarray | None:
        if point is not None:
            result = self._client.segment(rgb, point=[int(point[0]), int(point[1])])
        elif query:
            result = self._client.segment(rgb, text_prompt=query)
        else:
            raise ValueError("segment requires a point or a query")
        if not result.found or result.mask is None:
            return None
        return np.asarray(result.mask, dtype=bool)


__all__ = ["MolmoGrounder", "Sam3Segmenter"]
