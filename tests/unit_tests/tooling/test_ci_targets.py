# Copyright 2026 The RPent Authors.
"""Changed paths select exactly the installed components and simulator suites."""

from pathlib import Path

import pytest

from tests.tooling.ci_targets import SUITES, targets

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("path", "components"),
    [
        ("robots/robocasa/primitives.py", ["robot-robocasa"]),
        ("components/models/rldx/server.py", ["robot-robocasa"]),
        ("tests/e2e_tests/suites/libero.toml", ["robot-libero"]),
        ("tests/e2e_tests/suites/libero-plus.toml", ["robot-libero_plus"]),
        ("robots/libero_plus/component.toml", ["robot-libero_plus"]),
        (
            "components/models/sam3/model.py",
            ["robot-libero", "robot-libero_plus", "robot-robodojo"],
        ),
        ("tests/unit_tests/robots/robotwin/test_client.py", ["robot-robotwin"]),
        ("rpent/planner/api_loop.py", list(SUITES)),
        ("tests/e2e_tests/runner.py", list(SUITES)),
        ("docs/example.rst", []),
    ],
)
def test_select_consumers(path, components):
    assert targets([path, path], ROOT) == (
        components,
        [suite for component in components for suite in SUITES[component]],
    )
