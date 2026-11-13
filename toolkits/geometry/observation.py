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

"""Observation contract the host supplies to the geometry toolkit.

The toolkit does not open environment files or guess camera names. A host
implements :class:`~rpent.tools.observation.ObservationProvider` and returns an
:class:`~rpent.tools.observation.Observation` for the requested view and step.
The observation must carry RGB and at least one world-coordinate source:

- ``world_xyz``: authoritative per-pixel world coordinates, or
- ``depth`` plus ``intrinsics`` plus ``world_from_camera`` for on-demand
  back-projection.

``view`` and ``step`` identify the source frame in every result, so the planner
can relate a pixel to the image it measured. Grounding and segmentation are
optional host services; a missing service removes only that capability from
the tool schema.
"""

from __future__ import annotations

from rpent.tools.observation import (
    Grounder,
    Observation,
    ObservationError,
    ObservationProvider,
    Segmenter,
)

__all__ = [
    "Grounder",
    "Observation",
    "ObservationError",
    "ObservationProvider",
    "Segmenter",
]
