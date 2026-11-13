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

"""Capability gating in the shared tool families."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from rpent.tools.capabilities import Capabilities
from rpent.tools.motion_tools import MotionTools
from rpent.tools.policy_tools import PolicyTools
from rpent.tools.scene_tools import SceneTools
from toolkits.geometry.tool import GeometryTools


def _names(family, capabilities: Capabilities | None) -> set[str]:
    return {declaration.name for declaration in family.tools(capabilities)}


def test_scene_family_publishes_world_queries_only_with_depth() -> None:
    family = SceneTools(state=SimpleNamespace())

    assert _names(family, Capabilities()) == {"view_env_state"}
    assert _names(family, Capabilities(depth_views=("head",))) == {
        "view_env_state",
        "query_world_map",
    }


def test_geometry_family_requires_depth_and_calibration() -> None:
    family = GeometryTools(provider=SimpleNamespace())

    assert _names(family, Capabilities()) == set()
    assert _names(family, Capabilities(depth_views=("head",))) == set()
    assert _names(
        family, Capabilities(depth_views=("head",), calibrated_views=("head",))
    ) == {"geometry"}


def test_geometry_family_hides_target_without_a_grounder() -> None:
    family = GeometryTools(provider=SimpleNamespace())
    calibrated = Capabilities(depth_views=("head",), calibrated_views=("head",))

    declaration = family.tools(calibrated)[0]
    schema = declaration.input_schema
    assert "target" not in schema["properties"]
    assert schema["required"] == ["pixel"]
    assert "no grounding service" in declaration.description

    grounded = family.tools(replace(calibrated, grounding=True))[0]
    assert "target" in grounded.input_schema["properties"]
    assert grounded.input_schema.get("required", []) == []


def test_motion_family_requires_a_declared_step_transport() -> None:
    family = MotionTools(SimpleNamespace())

    assert _names(family, Capabilities()) == {
        "move_to",
        "rotate_wrist",
        "set_gripper",
        "release",
    }
    assert _names(family, Capabilities(execution={"reset": True})) == set()
    assert _names(family, Capabilities(execution={"step": True})) == {
        "move_to",
        "rotate_wrist",
        "set_gripper",
        "release",
    }


def test_policy_family_hides_a_backend_the_host_does_not_serve() -> None:
    binding = SimpleNamespace(backend="lingbot", tool_name="lingbot_act")

    assert _names(PolicyTools(binding), Capabilities()) == {"lingbot_act"}
    assert _names(PolicyTools(binding), Capabilities(policy_backends=("wam",))) == set()
    assert _names(PolicyTools(binding), Capabilities(policy_backends=("lingbot",))) == {
        "lingbot_act"
    }
