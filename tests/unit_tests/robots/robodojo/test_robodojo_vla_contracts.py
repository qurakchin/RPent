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

"""Lock the RoboDojo VLA wiring to the shared Pi0.5 components.

The branch once unconditionally imported and spawned local ``vla_client.py`` /
``vla_server.py`` files that do not exist in the repo, so ``rpent --robot
robodojo`` died in ``_init_runtime``. These tests pin the fixed wiring: the
runner must use the shared ``pi05_vla_client`` / ``pi05_vla_server`` pair with
``embodiment="robodojo"`` and never re-introduce the deleted local modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

from robots.robodojo import robot_spec

SHARED_CLIENT_MODULE = "rpent.robots.components.pi05_vla_client"
SHARED_SERVER_SCRIPT = "pi05_vla_server.py"
LEGACY_CLIENT_SYMBOL = "RoboDojoVLAClient"
LEGACY_CLIENT_MODULE = "robots.robodojo.vla_client"
LEGACY_SERVER_MODULE = "robots.robodojo.vla_server"


def _source() -> str:
    return Path(robot_spec.__file__).read_text(encoding="utf-8")


def _function_def(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"robot_spec has no function {name!r}")


def test_robot_spec_has_no_legacy_local_vla_modules() -> None:
    source = _source()

    assert LEGACY_CLIENT_SYMBOL not in source
    assert LEGACY_CLIENT_MODULE not in source
    assert LEGACY_SERVER_MODULE not in source


def test_robot_spec_imports_the_shared_pi05_client() -> None:
    tree = ast.parse(_source())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == SHARED_CLIENT_MODULE
        for alias in node.names
    }

    assert "Pi05VLAClient" in imported


def test_vla_component_connects_with_robodojo_embodiment() -> None:
    tree = ast.parse(_source())
    client_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Pi05VLAClient"
    ]

    assert client_calls, "the VLA component must construct Pi05VLAClient"
    embodiments = {
        keyword.value.value
        for call in client_calls
        for keyword in call.keywords
        if keyword.arg == "embodiment" and isinstance(keyword.value, ast.Constant)
    }
    assert embodiments == {"robodojo"}


def test_vla_server_spawn_uses_the_shared_server_script() -> None:
    tree = ast.parse(_source())
    spawn = _function_def(tree, "_spawn_vla_server")
    script_names = {
        node.value
        for node in ast.walk(spawn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert SHARED_SERVER_SCRIPT in script_names
