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

"""Translate RoboTwin planning and qpos transport to the motion protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from robots.robotwin.primitives import RoboTwinPrimitives


class RoboTwinMotionBackend:
    """Adapt RoboTwin's planner and action transport to ``MotionBackend``."""

    def __init__(self, primitives: RoboTwinPrimitives) -> None:
        self._primitives = primitives

    def check_cancelled(self) -> None:
        self._primitives._check_cancelled()

    def robot_state(self) -> Mapping[str, Any]:
        return self._primitives.env.last_info["robot_state"]

    def episode_status(self) -> Mapping[str, Any]:
        return self._primitives.env.last_info["episode_status"]

    def plan_arm_path(
        self, arm: str, target: Sequence[float]
    ) -> Mapping[str, Any]:
        return self._primitives.env.plan_arm_path(
            arm, np.asarray(target, dtype=np.float64)
        )

    def apply_qpos_updates(
        self, updates: list[dict[str, Any]]
    ) -> Mapping[str, Any]:
        return self._primitives.apply_qpos_updates(updates)

    def account_native_actions(self, count: int) -> None:
        self._primitives.native_actions += int(count)


__all__ = ["RoboTwinMotionBackend"]
