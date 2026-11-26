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

import os
from pathlib import Path

import pytest

from tests.e2e_tests.common import fast_wam_launch_argv, require_model_path
from tests.e2e_tests.robotwin.scenario import RoboTwinScenario


@pytest.fixture
def wam_argv() -> list[str]:
    require_model_path("ROBOTWIN_ASSETS_PATH")
    return [
        "--task-name",
        "beat_block_hammer",
        "--seed",
        "100000",
        "--task-config",
        "demo_randomized",
        "--max-episode-steps",
        "64",
        *fast_wam_launch_argv("RPENT_FAST_WAM_ROBOTWIN"),
    ]


@pytest.fixture
def lingbot_checkpoint() -> None:
    """Skip LingBot cases until the checkpoint and Qwen base are present."""
    model = require_model_path("LINGBOT_MODEL_PATH")
    if not (model / "qwen_base").is_dir():
        pytest.skip("LINGBOT_MODEL_PATH requires a qwen_base directory")


@pytest.fixture(scope="session")
def robotwin_scenario() -> RoboTwinScenario:
    return RoboTwinScenario(Path(os.environ["RPENT_E2E_OUTPUT_DIR"]))
