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

"""YAM robot config loader.

Users edit only ``config/example.yaml``: machine identity (follower CAN
channels, camera serials), site calibration (hand-eye extrinsics, work
surface), the primitive-control knobs, and the operator receipt path. Copy
that file to a site config and edit the values in place; the control defaults
ship in the same file rather than being restated in Python.

Task fields (name, language, seed, step budget) are CLI flags rather than
config values: the env server and the Agent must be started with the same
ones, and the runner already owns them on the Agent side.

``load_config`` flattens the YAML and the task fields into the dict
:class:`YamAgentEnv` and :class:`~robots.yam.cameras.YamRgbdCameraRig`
consume. Joint limits are not listed in the YAML; their YAM defaults live in
:mod:`robots.yam.geometry`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

DEFAULT_CONFIG = Path(__file__).with_name("config") / "example.yaml"

EPISODE_STEPS = 1000

# Task identity is a CLI concern: the runner already owns these on the Agent
# side, and the env server must be started with the same values. Listed here
# so a robot YAML that restates them is rejected instead of silently ignored.
TASK_KEYS = (
    "task_name",
    "task_language",
    "task_description",
    "seed",
    "max_episode_steps",
)


def load_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Load the robot YAML as a plain dict; ``None`` uses the packaged default."""
    config_path = Path(path).expanduser().resolve() if path else DEFAULT_CONFIG
    raw = OmegaConf.to_container(OmegaConf.load(config_path), resolve=True)
    if not isinstance(raw, dict):
        raise ValueError(f"YAM robot config must be a mapping: {config_path}")
    return raw


def load_config(
    path: str | Path | None = None,
    *,
    task_name: str,
    task_language: str | None = None,
    seed: int = 0,
    max_episode_steps: int = EPISODE_STEPS,
) -> dict[str, Any]:
    """Merge the robot YAML and the task fields into the flat consumer dict.

    The YAML supplies machine identity, site calibration, and the
    ``control`` section of primitive-control knobs; the latter is flattened so
    consumers read one flat mapping. Task fields come from CLI flags, and a
    YAML that restates them is rejected rather than silently overridden.

    An absent ``--task-language`` falls back to the task name with underscores
    opened up, matching the Agent-side instruction in ``robot_spec``.
    """
    if not str(task_name or "").strip():
        raise ValueError("task_name is required")
    raw = load_mapping(path)
    duplicated = sorted(set(raw) & set(TASK_KEYS))
    if duplicated:
        raise ValueError(
            f"task fields must come from CLI flags, not the robot YAML: {duplicated}"
        )
    control = raw.pop("control", {})
    if not isinstance(control, dict):
        raise ValueError("control must be a mapping of primitive-control knobs")
    language = str(task_language).strip() if task_language else ""
    if not language:
        language = str(task_name).replace("_", " ")
    return {
        **raw,
        **control,
        "task_name": str(task_name),
        "task_language": language,
        "seed": int(seed),
        "max_episode_steps": int(max_episode_steps),
    }
