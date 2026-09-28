# Copyright 2026 The RPent Authors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at https://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from robots.yam import runtime_config

# Every control knob a consumer indexes directly; the packaged YAML must
# carry all of them because ``load_config`` supplies no Python defaults.
CONTROL_KEYS = (
    "max_joint_delta_per_step",
    "feedback_timeout_s",
    "camera_frame_timeout_s",
    "camera_warmup_frames",
    "table_clearance_m",
    "path_joint_delta",
    "qpos_static_tolerance_rad",
)


def test_packaged_example_config_carries_identity_and_control_knobs() -> None:
    raw = runtime_config.load_mapping()

    assert set(raw["robot"]) == {"left_follower", "right_follower"}
    assert raw["robot"]["left_follower"]["channel"] == "can0"
    assert raw["robot"]["right_follower"]["channel"] == "can1"
    assert [camera["name"] for camera in raw["cameras"]] == ["top", "left", "right"]
    assert raw["operator_receipt_path"]
    assert set(raw["control"]) == set(CONTROL_KEYS)
    # Task fields come from CLI flags, never the YAML.
    for key in ("task_name", "seed"):
        assert key not in raw


def test_load_config_flattens_control_section_and_sets_task_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "robot.yaml"
    path.write_text(
        "robot: {}\ncameras: []\ncontrol:\n  max_joint_delta_per_step: 0.02\n"
        "  table_clearance_m: 0.05\n",
        encoding="utf-8",
    )

    config = runtime_config.load_config(
        path, task_name="pick_place", seed=7, max_episode_steps=42
    )

    assert config["task_name"] == "pick_place"
    assert config["task_language"] == "pick place"
    assert config["seed"] == 7
    assert config["max_episode_steps"] == 42
    assert config["max_joint_delta_per_step"] == 0.02
    assert config["table_clearance_m"] == 0.05
    assert "control" not in config
    # The YAML is the only source of control knobs: nothing is invented.
    assert "path_joint_delta" not in config


def test_load_config_rejects_non_mapping_control_section(tmp_path: Path) -> None:
    path = tmp_path / "robot.yaml"
    path.write_text(
        "robot: {}\ncameras: []\ncontrol: [1, 2]\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="control must be a mapping"):
        runtime_config.load_config(path, task_name="pick_place")


def test_load_config_rejects_task_fields_in_yaml(tmp_path: Path) -> None:
    path = tmp_path / "robot.yaml"
    path.write_text(
        "robot: {}\ncameras: []\ntask_name: stale\nmax_episode_steps: 5\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="task fields must come from CLI"):
        runtime_config.load_config(path, task_name="fresh")


def test_load_config_rejects_blank_task_name() -> None:
    with pytest.raises(ValueError, match="task_name"):
        runtime_config.load_config(None, task_name="  ")


def test_env_server_cli_builds_matching_task_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import robots.yam.env_server as env_server
    import robots.yam.rlinf_env as rlinf_env

    captured: dict[str, Any] = {}

    class FakeEnv:
        def __init__(self, config: dict[str, Any]) -> None:
            captured["config"] = config

    class FakeFacade:
        def __init__(self, env: Any, *, metadata: Any = None) -> None:
            captured["metadata"] = metadata

        def serve(self, **kwargs: Any) -> None:
            captured["serve"] = kwargs

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(rlinf_env, "YamAgentEnv", FakeEnv)
    monkeypatch.setattr(env_server, "YamEnvFacade", FakeFacade)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "env_server",
            "--task-name",
            "pick_place",
            "--seed",
            "4",
            "--max-episode-steps",
            "77",
        ],
    )

    env_server.main()

    config = captured["config"]
    assert config["task_name"] == "pick_place"
    assert config["task_language"] == "pick place"
    assert config["seed"] == 4
    assert config["max_episode_steps"] == 77
    metadata = captured["metadata"]
    assert metadata["task_name"] == "pick_place"
    assert metadata["seed"] == 4
    assert metadata["execution"]["step_limit"] == 77
    assert captured["closed"] is True
