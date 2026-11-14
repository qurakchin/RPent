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

"""Run artifacts record which installation produced them."""

import json

from rpent.install.fingerprint import fingerprint_sha256, write_fingerprint
from rpent.install.snapshot import installation_snapshot, record_run_environment


def _fingerprint():
    return {
        "schema": 1,
        "profile": "minimal",
        "python": "3.11.14",
        "platform": "linux-x86_64",
        "components": {"rlinf": {"placement": "in-env"}},
        "source_commit": "abc123",
        "source_dirty": False,
    }


def test_snapshot_of_a_venv_without_a_fingerprint(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()

    snapshot = installation_snapshot(venv)

    assert snapshot["profile"] is None
    assert snapshot["install_sha256"] is None
    assert snapshot["venv"] == str(venv.resolve())
    assert snapshot["components"] == []


def test_snapshot_identifies_the_installed_profile(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    fingerprint = _fingerprint()
    write_fingerprint(venv, fingerprint)

    snapshot = installation_snapshot(venv)

    assert snapshot["profile"] == "minimal"
    assert snapshot["install_sha256"] == fingerprint_sha256(fingerprint)
    assert snapshot["components"] == ["rlinf"]
    assert snapshot["source_commit"] == "abc123"


def test_record_merges_into_an_existing_run_manifest(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    write_fingerprint(venv, _fingerprint())
    (tmp_path / "run.json").write_text(
        json.dumps({"schema": 1, "task": "open the drawer", "started_at": "then"}),
        encoding="utf-8",
    )

    record_run_environment(tmp_path, venv=venv)

    record = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert record["task"] == "open the drawer"
    assert record["started_at"] == "then"
    assert record["environment"]["profile"] == "minimal"


def test_record_creates_the_manifest_and_is_idempotent(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    write_fingerprint(venv, _fingerprint())

    record_run_environment(tmp_path, venv=venv)
    first = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    record_run_environment(tmp_path, venv=venv)
    second = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    assert first["schema"] == 1
    assert first["environment"] == second["environment"]
    assert first["started_at"] == second["started_at"]
