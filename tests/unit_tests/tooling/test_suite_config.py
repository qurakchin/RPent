# Copyright 2026 The RPent Authors.
"""Declarative E2E suite config discovery, resolution, and skip detection."""

from tests.e2e_tests.suite import (
    discover_suites,
    load_suite,
    resolve_case,
    resolve_value,
)


def test_discover_all_repo_suites():
    suites = discover_suites()
    assert set(suites) == {
        "libero",
        "libero-plus",
        "libero-pro",
        "robocasa",
        "robodojo",
        "robolab",
        "robotwin",
    }
    for name, suite in suites.items():
        assert suite["component"].startswith("robot-"), name
        assert suite["cases"], name


def test_resolve_value_handles_shared_paths_and_placeholders():
    assert (
        resolve_value("models/sam3/sam3.pt", shared="/shared")
        == "/shared/models/sam3/sam3.pt"
    )
    assert resolve_value("assets/libero", shared="/shared") == "/shared/assets/libero"
    assert (
        resolve_value(
            "{output_dir}/cfg:{gpu}:{env:MY_ENDPOINT}",
            shared="/shared",
            output_dir="/out",
            gpu="3",
            environ={"MY_ENDPOINT": "http://127.0.0.1:9000"},
        )
        == "/out/cfg:3:http://127.0.0.1:9000"
    )


def test_resolve_case_detects_missing_shared_resources_and_external_overrides(tmp_path):
    shared = tmp_path / "shared"
    (shared / "assets/robolab").mkdir(parents=True)
    (shared / "venvs/robolab-sim/bin").mkdir(parents=True)
    (shared / "venvs/robolab-sim/bin/python").write_text("", encoding="utf-8")

    suite = load_suite("robolab")
    resolved = resolve_case(
        suite,
        suite["cases"][0],
        output_dir=tmp_path / "out",
        gpu="0",
        environ={"RPENT_SHARED_ROOT": str(shared)},
    )
    assert any("RLinf-Pi05-RoboLab-droid-jointpos" in m for m in resolved["missing"])

    # External env var overrides the TOML default automatically.
    custom_ckpt = tmp_path / "custom-ckpt"
    custom_ckpt.mkdir()
    overridden = resolve_case(
        suite,
        suite["cases"][0],
        output_dir=tmp_path / "out",
        gpu="0",
        environ={
            "RPENT_SHARED_ROOT": str(shared),
            "PI05_CHECKPOINT_PATH": str(custom_ckpt),
        },
    )
    assert overridden["missing"] == []
    assert overridden["env"]["PI05_CHECKPOINT_PATH"] == str(custom_ckpt)

    libero = load_suite("libero")
    cosmos_case = next(c for c in libero["cases"] if c["name"] == "cosmos3")
    resolved_cosmos = resolve_case(
        libero,
        cosmos_case,
        output_dir=tmp_path / "out",
        gpu="0",
        environ={"RPENT_SHARED_ROOT": str(shared)},
    )
    assert any("RPENT_COSMOS3_ENDPOINT" in m for m in resolved_cosmos["missing"])
