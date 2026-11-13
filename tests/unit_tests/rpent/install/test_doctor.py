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

"""Doctor reports missing, stale, and endpoint-reachable installations."""

import socket

from rpent.install.discovery import discover
from rpent.install.doctor import (
    FAIL,
    OK,
    WARN,
    _endpoint_address,
    _probe_endpoint,
    check_installation,
    inspect_installation,
)
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    fingerprint_sha256,
    runtime_platform,
    write_fingerprint,
)
from rpent.install.installer import resolve_install_target
from rpent.install.requirements import requirements_sha256


def _profile(write_toml, *, core=False):
    write_toml(
        "envs/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "3.11"
        platform = "{runtime_platform()}"
        core = {str(core).lower()}
        """,
    )


def _venv(tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    return venv


def test_missing_fingerprint_reports_install_command(tmp_path):
    checks = check_installation(tmp_path / "venv", root=tmp_path)

    assert checks[0].status == FAIL
    assert "rpent-env install <profile>" in checks[0].message


def test_stale_fingerprint_fails_before_running_checks(
    tmp_path, write_toml, monkeypatch
):
    _profile(write_toml)
    venv = _venv(tmp_path)
    write_fingerprint(
        venv,
        {
            "profile": "alpha",
            "python": "3.11.9",
            "requirements_sha256": "stale",
            "include_dev": False,
        },
    )

    def _missing_uv():
        raise InstallError("uv missing")

    monkeypatch.setattr("rpent.install.doctor.find_uv", _missing_uv)

    checks = check_installation(venv, root=tmp_path)

    assert [check.status for check in checks[:3]] == [OK, OK, FAIL]
    assert "out of date" in checks[2].message
    assert any(
        check.status == WARN and "uv missing" in check.message for check in checks
    )


def test_dev_installation_is_not_reported_as_stale(tmp_path, write_toml, monkeypatch):
    _profile(write_toml)
    write_toml(
        "envs/dev.toml",
        f"""
        schema = 1
        name = "dev"
        python = "3.11"
        platform = "{runtime_platform()}"
        core = false
        dependencies = ["pytest"]
        """,
    )
    venv = _venv(tmp_path)
    resolution = resolve_install_target(
        "alpha", discover(tmp_path), root=tmp_path, include_dev=True
    )
    assert resolution.ok
    write_fingerprint(
        venv,
        {
            "profile": "alpha",
            "python": "3.11.9",
            "include_dev": True,
            "requirements_sha256": requirements_sha256(resolution, include_dev=True),
        },
    )

    def _missing_uv():
        raise InstallError("uv missing")

    monkeypatch.setattr("rpent.install.doctor.find_uv", _missing_uv)

    checks = check_installation(venv, root=tmp_path)

    assert any(
        check.status == OK and "manifests unchanged" in check.message
        for check in checks
    )
    assert not any("out of date" in check.message for check in checks)


def test_inspect_installation_reports_fingerprint_hash(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    fingerprint = {"profile": "alpha"}
    write_fingerprint(venv, fingerprint)

    inspected = inspect_installation(venv)

    assert inspected["fingerprint"] == fingerprint
    assert inspected["sha256"] == fingerprint_sha256(fingerprint)
    assert inspect_installation(tmp_path / "missing") is None


def test_endpoint_address_accepts_host_port_and_url():
    assert _endpoint_address("host:8000") == ("host", 8000)
    assert _endpoint_address("http://host:8000/path") == ("host", 8000)
    assert _endpoint_address("host") is None


def test_probe_endpoint_reports_reachable_and_unreachable():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        host, port = server.getsockname()
        assert _probe_endpoint(f"{host}:{port}") is None

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()
    message = _probe_endpoint(f"{host}:{port}")
    assert "not reachable" in message
