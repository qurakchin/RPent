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

"""Capability snapshot and the tool-family registration contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from rpent.tools.base import Tool


@dataclass(frozen=True)
class Capabilities:
    """What the connected environment and services actually provide.

    Values come from the adapter's environment metadata and from services that
    were actually connected at runtime; configuration flags alone must not
    claim a capability.
    """

    env: Mapping[str, Any] = field(default_factory=dict)
    execution: Mapping[str, Any] = field(default_factory=dict)
    segmentation: bool = False
    grounding: bool = False
    policy_backends: tuple[str, ...] = ()
    real_robot: bool = False
    depth_views: tuple[str, ...] = ()
    calibrated_views: tuple[str, ...] = ()
    native_tools: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for run metadata."""
        return {
            "env": dict(self.env),
            "execution": dict(self.execution),
            "segmentation": self.segmentation,
            "grounding": self.grounding,
            "policy_backends": list(self.policy_backends),
            "real_robot": self.real_robot,
            "depth_views": list(self.depth_views),
            "calibrated_views": list(self.calibrated_views),
            "native_tools": list(self.native_tools),
        }

    def has_depth(self, view: str | None = None) -> bool:
        """Whether a view exposes metric depth for spatial queries."""
        if view is None:
            return bool(self.depth_views)
        return view in self.depth_views

    def has_calibration(self, view: str | None = None) -> bool:
        """Whether a view exposes intrinsics and a camera pose."""
        if view is None:
            return bool(self.calibrated_views)
        return view in self.calibrated_views


class ToolFamily:
    """A capability-gated group of declarations.

    Families only register and trim tools. Implementations that need their own
    evaluation corpus live under ``toolkits/``.
    """

    name = "tools"

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> Sequence[Tool]:
        """Return declarations for the connected capabilities."""
        raise NotImplementedError


__all__ = ["Capabilities", "ToolFamily"]
