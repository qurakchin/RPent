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

"""RoboTwin capability declarations shared by runtime and schema snapshots.

Both paths call :func:`build_capabilities`; declared tools supply the runtime
contract from ``robot_spec`` and the same connected-service facts, so a family
cannot gain a gate in one path and silently drift in the other.
"""

from __future__ import annotations

from typing import Any, Mapping

from rpent.tools.capabilities import Capabilities


def connected_policy_backend(model: Any, declared: str) -> str:
    """Return the backend of the connected client, not the requested one.

    ``policy_kind`` travels with the runtime arguments, so a mismatched
    declaration could otherwise make the policy capability self-certify. The
    concrete client is the runtime evidence; unknown test doubles keep the
    declaration.
    """
    from robots.robotwin.vla_client import LingBotVLAClient
    from robots.robotwin.wam_client import RoboTwinWAMClient

    if isinstance(model, RoboTwinWAMClient):
        return "wam"
    if isinstance(model, LingBotVLAClient):
        return "lingbot"
    return declared


def declared_views(
    server_meta: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the depth and calibrated camera views advertised by the server."""
    extensions = server_meta.get("extensions")
    extensions = extensions if isinstance(extensions, dict) else {}
    render_camera = extensions.get("render_camera")
    render_camera = render_camera if isinstance(render_camera, dict) else {}
    names = tuple(render_camera.get("camera_names") or ())
    depth_views = names if render_camera.get("metric_depth") is True else ()
    calibrated_views = names if extensions.get("get_camera_meta") is True else ()
    return depth_views, calibrated_views


def build_capabilities(
    *,
    server_meta: Mapping[str, Any],
    execution: Mapping[str, Any] | None = None,
    segmentation: bool = False,
    grounding: bool = False,
    policy_backends: tuple[str, ...] = (),
    real_robot: bool = False,
    depth: bool = True,
) -> Capabilities:
    """Build the one capability snapshot used by registration and snapshots.

    Args:
        server_meta: Runtime contract returned by the env server.
        execution: Execution methods the connected env declares.
        segmentation: Whether a segmenter was connected.
        grounding: Whether a grounder was connected.
        policy_backends: Backends whose clients are connected.
        real_robot: Whether the slice drives physical hardware.
        depth: Whether to advertise the server's depth and calibrated views.
            Declared snapshots can disable it to cover hosts without depth.
    """
    depth_views, calibrated_views = declared_views(server_meta) if depth else ((), ())
    return Capabilities(
        env=dict(server_meta),
        execution=dict(execution or {}),
        segmentation=segmentation,
        grounding=grounding,
        policy_backends=tuple(policy_backends),
        real_robot=real_robot,
        depth_views=depth_views,
        calibrated_views=calibrated_views,
    )


def declared_capabilities(
    *,
    server_meta: Mapping[str, Any],
    policy_kind: str = "vla",
    grounding: bool = False,
    depth: bool = True,
) -> Capabilities:
    """Build the snapshot used by :meth:`RoboTwinToolkit.declared_tools`."""
    backend = "wam" if policy_kind == "wam" else "lingbot"
    return build_capabilities(
        server_meta=server_meta,
        execution={"reset": True, "step": True, "chunk_step": True},
        grounding=grounding,
        policy_backends=(backend,),
        depth=depth,
    )


__all__ = [
    "build_capabilities",
    "connected_policy_backend",
    "declared_capabilities",
    "declared_views",
]
