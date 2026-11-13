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

import pytest
from pydantic import ValidationError

from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.tools.capabilities import Capabilities
from rpent.tools.motion_tools import MotionTools
from rpent.tools.policy_tools import PolicyTools
from rpent.tools.scene_tools import SceneTools
from rpent.tools.toolkit import Toolkit
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
    assert schema["properties"]["pixel"]["type"] == "array"
    assert "no grounding service" in declaration.description
    assert "target" not in declaration.args_schema.model_fields

    grounded = family.tools(replace(calibrated, grounding=True))[0]
    assert "target" in grounded.input_schema["properties"]
    assert grounded.input_schema.get("required", []) == []


def test_published_geometry_schema_matches_runtime_validation() -> None:
    family = GeometryTools(provider=SimpleNamespace())
    declaration = family.tools(
        Capabilities(depth_views=("head",), calibrated_views=("head",))
    )[0]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        declaration.args_schema.model_validate(
            {"target": "the red block", "pixel": [10, 20]}, strict=True
        )
    with pytest.raises(ValidationError, match="Field required"):
        declaration.args_schema.model_validate({}, strict=True)
    assert declaration.args_schema.model_validate(
        {"pixel": [10, 20]}, strict=True
    ).pixel == [10, 20]


def test_toolkit_reports_a_rejected_target_as_a_call_failure(tmp_path) -> None:
    toolkit = Toolkit(
        dashboard_events=NullDashboardEventSink(),
        memory=MemoryManager(tmp_path / "memory"),
    )
    toolkit.add_tools(
        GeometryTools(provider=SimpleNamespace()),
        capabilities=Capabilities(depth_views=("head",), calibrated_views=("head",)),
    )

    result = toolkit.execute_tool("geometry", {"target": "the red block"})

    assert result.call_ok is False
    assert result.error["code"] == "validation"
    assert result.no_execution is True


def test_policy_family_logs_an_undeclared_backend(caplog) -> None:
    family = PolicyTools(
        SimpleNamespace(backend="lingbot", tool_name="lingbot_act"),
    )

    with caplog.at_level("WARNING", logger="rpent.tools.policy"):
        assert family.tools(Capabilities(policy_backends=("wam",))) == ()

    assert "not declared" in caplog.text
    assert "lingbot" in caplog.text


def test_geometry_family_logs_which_capability_is_missing(caplog) -> None:
    family = GeometryTools(provider=SimpleNamespace())

    with caplog.at_level("INFO", logger="rpent.toolkits.geometry"):
        assert family.tools(Capabilities(depth_views=("head",))) == ()

    assert "geometry tool omitted" in caplog.text
    assert "calibrated_views" in caplog.text


def test_motion_family_requires_a_declared_step_transport() -> None:
    family = MotionTools(SimpleNamespace())

    assert _names(family, Capabilities()) == set()
    assert _names(family, Capabilities(execution={"reset": True})) == set()
    assert _names(family, Capabilities(execution={"step": True})) == {
        "move_to",
        "rotate_wrist",
        "set_gripper",
        "release",
    }
    assert _names(family, Capabilities(execution={"chunk_step": True})) == {
        "move_to",
        "rotate_wrist",
        "set_gripper",
        "release",
    }
    # Without a capability snapshot, the family keeps its legacy behaviour.
    assert _names(family, None) == {
        "move_to",
        "rotate_wrist",
        "set_gripper",
        "release",
    }


def test_policy_family_hides_a_backend_the_host_does_not_serve() -> None:
    binding = SimpleNamespace(backend="lingbot", tool_name="lingbot_act")

    assert _names(PolicyTools(binding), Capabilities()) == set()
    assert _names(PolicyTools(binding), Capabilities(policy_backends=("wam",))) == set()
    assert _names(PolicyTools(binding), Capabilities(policy_backends=("lingbot",))) == {
        "lingbot_act"
    }
    assert _names(PolicyTools(binding), None) == {"lingbot_act"}
