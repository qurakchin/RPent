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

"""Registry contracts for the RoboDojo backend."""

from __future__ import annotations

import robots.robodojo
from rpent.robots import enumerate_robots, get_robot_spec
from rpent.robots.robot_spec import RobotSpec


def test_enumerate_robots_includes_robodojo() -> None:
    assert "robodojo" in enumerate_robots()


def test_robodojo_package_exposes_spec_and_toolkit_factories() -> None:
    assert callable(robots.robodojo.get_robot_spec)
    assert callable(robots.robodojo.get_toolkit)


def test_get_robot_spec_returns_named_robodojo_spec() -> None:
    spec = get_robot_spec("robodojo")

    assert isinstance(spec, RobotSpec)
    assert spec.name == "robodojo"
    assert callable(spec.add_cli_args)
    assert callable(spec.parse_config)
    assert callable(spec.init_runtime)
