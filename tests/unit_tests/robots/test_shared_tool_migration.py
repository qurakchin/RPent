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

"""Keep the remaining slice-local motion implementations visible.

The shared ``MotionTools`` family is the target for every slice. Until the a_5
adapter contract supplies ``step_pose`` / ``step_joints``, each slice keeps its
own transport implementation. This inventory fails when a new duplicate appears
or when a migration removes one without updating the remaining-work table.
Transport methods in ``env_client`` / ``env_server`` / manual-call helpers are a
different layer and stay.
"""

from __future__ import annotations

import ast
from pathlib import Path

from robots.robotwin.toolkit import RoboTwinToolkit
from rpent.tools.motion_tools import MotionTools

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROBOTS = _REPO_ROOT / "robots"
_SHARED_MOTION_TOOLS = {"move_to", "rotate_wrist", "set_gripper", "release"}
_SLICE_MOTION_TOOLS = {"rotate_pitch", "move_pose"}

# Shared-family implementations still owned by a slice. The a_3 target is an
# empty table; a migration should delete the entries it removes.
_LOCAL_SHARED_MOTION = {
    "robots/libero/tools.py": {
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
    "robots/robocasa/primitives.py": {"move_to", "release", "set_gripper"},
    "robots/robodojo/primitives.py": {
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
    "robots/yam/primitives.py": {
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
    "robots/yam/toolkit.py": {
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
}

# Motion entry points the shared family does not replace.
_LOCAL_SLICE_MOTION = {
    "robots/libero/tools.py": {"move_pose", "rotate_pitch"},
    "robots/robocasa/primitives.py": {"rotate_pitch"},
}

# RPC and manual-call helpers, not model-facing tool declarations.
_MOTION_TRANSPORTS = {
    "robots/dual_franka/dual_franka_manual_call.py": {"set_gripper"},
    "robots/dual_franka/env_client.py": {"set_gripper"},
    "robots/dual_franka/env_server.py": {"set_gripper"},
    "robots/franka/env_client.py": {"set_gripper"},
    "robots/franka/env_server.py": {"set_gripper"},
}


def _definitions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _motion_definitions() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(_ROBOTS.rglob("*.py")):
        names = _definitions(path) & (_SHARED_MOTION_TOOLS | _SLICE_MOTION_TOOLS)
        if names:
            found[path.relative_to(_REPO_ROOT).as_posix()] = names
    return found


def test_local_motion_implementations_match_the_migration_baseline() -> None:
    definitions = _motion_definitions()
    local_paths = set(_LOCAL_SHARED_MOTION) | set(_LOCAL_SLICE_MOTION)

    def surface(allowed: set[str]) -> dict[str, set[str]]:
        return {
            path: names & allowed
            for path, names in definitions.items()
            if path in local_paths and names & allowed
        }

    assert surface(_SHARED_MOTION_TOOLS) == _LOCAL_SHARED_MOTION
    assert surface(_SLICE_MOTION_TOOLS) == _LOCAL_SLICE_MOTION
    transports = {
        path: names for path, names in definitions.items() if path in _MOTION_TRANSPORTS
    }
    assert transports == _MOTION_TRANSPORTS
    assert set(definitions) == local_paths | set(_MOTION_TRANSPORTS)


def test_robotwin_motion_declarations_come_from_the_shared_family() -> None:
    declarations = {spec.name: spec for spec in RoboTwinToolkit.declared_tools()}

    for name in sorted(_SHARED_MOTION_TOOLS):
        assert isinstance(declarations[name].handler.__self__, MotionTools)
