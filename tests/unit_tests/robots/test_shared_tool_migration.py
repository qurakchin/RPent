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

RoboDojo keeps its native motion tools until the a_5 contract can carry their
execution truth. Its transport reports confirmed partial progress, marks a
timed-out mutation as ``execution_unknown``, and returns the reason each command
stopped (``plan_failed``, ``rejected``, ``synchronization_lost``, ...).
``MotionBackend`` has no field for any of that, so migrating now would replace
verified execution states with the shared family's coarser ones.

RoboTwin already uses the shared families. Its migration from the base module
added ``recall``/``remember``/``corroborate`` and ``geometry``, and removed
``sample_world_xyz``; ``geometry`` fits a mask's point cloud, so it is not a
renamed single-pixel query. ``reset`` stays a RoboTwin tool registered only in
exploration mode, which is why the migrated declaration snapshot does not list
it. ``test_tool_schema_contracts`` pins that delta.

The declaration ledger below records the remaining slices that redeclare a
shared tool name on purpose. Each entry has a reason: their ``view_env_state``
payloads are their action-tool payloads, ``finish`` overrides add the native
episode verdict, and the YAM world queries use YAM-only view literals.
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


# Slice modules that declare a tool whose name a shared family also owns.
# ``view_env_state`` is their action-tool payload for the current step;
# ``finish`` adds the native episode verdict; the YAM world queries accept
# YAM-only view literals. Motion entries leave when a_5 lands.
_LOCAL_SHARED_DECLARATIONS = {
    "robots/dual_franka/tools.py": {"view_env_state"},
    "robots/franka/tools.py": {"view_env_state"},
    "robots/libero/tools.py": {
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
        "view_env_state",
    },
    "robots/robocasa/primitives.py": {"move_to", "release", "set_gripper"},
    "robots/robocasa/tools.py": {"finish", "query_world_map", "view_env_state"},
    "robots/robodojo/primitives.py": {
        "finish",
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
    "robots/robodojo/tools.py": {"view_env_state"},
    "robots/robotwin/primitives.py": {"finish"},
    "robots/yam/toolkit.py": {
        "finish",
        "move_to",
        "release",
        "rotate_wrist",
        "set_gripper",
    },
    "robots/yam/tools.py": {
        "query_world_map",
        "sample_world_xyz",
        "view_env_state",
    },
}

_SHARED_DECLARATION_ROOTS = ("rpent/tools", "toolkits")


def _declared_tool_names(path: Path) -> set[str]:
    """Return the names a module declares through the ``tool`` decorator."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if not (isinstance(target, ast.Name) and target.id == "tool"):
                continue
            name = node.name
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        name = keyword.value.value
            names.add(name)
    return names


def _slice_shared_declarations() -> dict[str, set[str]]:
    shared = {
        name
        for base in _SHARED_DECLARATION_ROOTS
        for path in (_REPO_ROOT / base).rglob("*.py")
        for name in _declared_tool_names(path)
    }
    found: dict[str, set[str]] = {}
    for path in sorted(_ROBOTS.rglob("*.py")):
        names = _declared_tool_names(path) & shared
        if names:
            found[path.relative_to(_REPO_ROOT).as_posix()] = names
    return found


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


def test_slice_declarations_of_shared_names_match_the_ownership_ledger() -> None:
    """Every slice redeclaration of a shared name must be recorded.

    A new entry means a slice started its own implementation of a shared tool;
    a missing entry means a migration removed one without updating the ledger.
    """
    assert _slice_shared_declarations() == _LOCAL_SHARED_DECLARATIONS
