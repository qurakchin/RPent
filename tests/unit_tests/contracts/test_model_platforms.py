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

"""Robot slices own the wire contracts; model services keep matching copies."""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from robots.libero import control as libero_control
from robots.robodojo import access as robodojo_access
from robots.robotwin import contracts as robotwin_contracts
from robots.robotwin import control as robotwin_control
from robots.robotwin import observation as robotwin_observation
from robots.yam import contracts as yam_contracts

MODEL_PLATFORMS = Path(__file__).resolve().parents[3] / "components" / "models"
#: Files that hold a model-side copy of a robot-owned contract.
COPY_FILES = ("platforms.py", "contracts.py")
#: Every constant a model-side copy may define, with the robot-side owner it
#: must match. A new copy has to be registered here, so it cannot escape the
#: drift check by living in a module this test does not name.
PROVIDERS = {
    "LIBERO_OSC": libero_control.LIBERO_OSC,
    "ROBOTWIN_QPOS": robotwin_control.ROBOTWIN_QPOS,
    "ROBOTWIN_CAMERAS": robotwin_observation.ROBOTWIN_CAMERAS,
    "YAM_VLA_CONTRACT": yam_contracts.YAM_VLA_CONTRACT,
    "CAMERAS": robodojo_access.CAMERAS,
    "ARX_X5_JOINT_FIELDS": robodojo_access.ARX_X5_JOINT_FIELDS,
    "LINGBOT_MODEL_SPEC": dataclasses.asdict(robotwin_contracts.MODEL_SPEC),
}


def _model_platforms() -> dict[str, ModuleType]:
    """Import every model-side copy module."""
    paths = sorted(
        path for name in COPY_FILES for path in MODEL_PLATFORMS.glob(f"*/{name}")
    )
    assert paths, f"no model platform copies under {MODEL_PLATFORMS}"
    return {
        f"components.models.{path.parent.name}.{path.stem}": importlib.import_module(
            f"components.models.{path.parent.name}.{path.stem}"
        )
        for path in paths
    }


def test_every_model_platform_copy_matches_its_provider():
    for name, module in _model_platforms().items():
        copied = {key for key in vars(module) if key.isupper()}
        assert copied, f"{name} defines no contract copy"
        unknown = sorted(copied - PROVIDERS.keys())
        assert not unknown, (
            f"{name} defines {unknown}; register each copy and its robot-side "
            "owner in PROVIDERS"
        )
        for key in copied:
            assert getattr(module, key) == PROVIDERS[key], (
                f"{name}:{key} drifted from the robot contract"
            )


def test_model_copies_are_independent_of_the_robot_modules():
    # A model service may not import a robot slice, so the two sides are
    # separate objects that the drift test keeps equal.
    for module in _model_platforms().values():
        for key in vars(module):
            if key.isupper():
                assert getattr(module, key) is not PROVIDERS[key]


def test_yam_copies_report_the_control_station_identity():
    platforms = _model_platforms()
    for name in ("apxinf", "openpi"):
        contract = platforms[f"components.models.{name}.platforms"].YAM_VLA_CONTRACT
        assert contract == yam_contracts.vla_runtime_contract()
        assert contract["camera_order"] == ["top", "left", "right"]
        assert contract["state_layout"] == "qpos14"
        assert contract["action_layout"] == "qpos14"
        assert contract["action_dim"] == 14


def test_awomo05_rgb_check_matches_the_robot_slice():
    from components.models.awomo05 import contracts as awomo05_contracts

    valid = {
        "vision": {
            name: {"color": np.zeros((2, 3, 3), dtype=np.uint8)}
            for name in robodojo_access.CAMERAS
        }
    }
    awomo05_contracts.validate_rgb(valid)
    robodojo_access.validate_rgb(valid)

    invalid = [
        {"vision": {}},
        {
            "vision": {
                name: {"color": np.zeros((2, 3, 3), dtype=np.float32)}
                for name in robodojo_access.CAMERAS
            }
        },
        {
            "vision": {
                name: {"color": np.zeros((2, 3), dtype=np.uint8)}
                for name in robodojo_access.CAMERAS
            }
        },
    ]
    for observation in invalid:
        with pytest.raises(ValueError) as expected:
            robodojo_access.validate_rgb(observation)
        with pytest.raises(ValueError) as copied:
            awomo05_contracts.validate_rgb(observation)
        assert str(copied.value) == str(expected.value)


def test_lingbot_runtime_contract_matches_the_robot_slice():
    from components.models.lingbot import contracts as lingbot_contracts

    assert (
        lingbot_contracts.vla_runtime_contract()
        == robotwin_contracts.vla_runtime_contract()
    )
