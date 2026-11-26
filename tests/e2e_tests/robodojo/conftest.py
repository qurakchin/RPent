# Copyright 2026 The RPent Authors.
"""RoboDojo simulator and model service configuration."""

import os
from collections.abc import Callable

import pytest

from tests.e2e_tests.common import require_model_path


@pytest.fixture
def robodojo_runtime_argv() -> list[str]:
    """Use a separate simulator interpreter when provisioned."""
    if sim_python := os.getenv("ROBODOJO_SIM_PYTHON"):
        return ["--sim-python", sim_python]
    return []


@pytest.fixture
def robodojo_model_argv(robodojo_runtime_argv) -> Callable[[str], list[str]]:
    """Use the local checkpoint and worker interpreter for the selected model."""

    def model_argv(backend: str) -> list[str]:
        prefix = backend.upper()
        checkpoint = require_model_path(f"{prefix}_MODEL_PATH")
        python = require_model_path(f"RPENT_{prefix}_PYTHON", file=True)
        return [
            *robodojo_runtime_argv,
            "--am-backend",
            backend,
            "--am-checkpoint",
            str(checkpoint),
            "--am-python",
            str(python),
        ]

    return model_argv
