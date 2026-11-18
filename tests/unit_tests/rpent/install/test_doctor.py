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
)
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    fingerprint_sha256,
    write_fingerprint,
)
from rpent.install.installer import target_resolution
from rpent.install.requirements import REQUIREMENTS_SCHEMA, requirements_sha256


def _target(write_toml, *, core=False, lock=None):
    declared = f'lock = "{lock}"\n' if lock else ""
    write_toml(
        "installs/targets/alpha.toml",
        f"""
        schema = 2
        kind = "target"
        name = "alpha"
        python = "3.11"
        core = {str(core).lower()}
        {declared}
        """,
    )


def _venv(tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    return venv


def _without_uv(monkeypatch):
    def _missing_uv():
        raise InstallError("uv missing")

    monkeypatch.setattr("rpent.install.doctor.find_uv", _missing_uv)


def _inputs_hash(root, name="alpha"):
    resolution = target_resolution(name, discover(root), root=root)
    return requirements_sha256(resolution, root=root)


def test_missing_fingerprint_reports_install_command(tmp_path):
    checks = check_installation(tmp_path / "venv", root=tmp_path)

    assert checks[0].status == FAIL
    assert "rpent-install install <target>" in checks[0].message


def test_unchanged_inputs_are_accepted(tmp_path, write_toml, monkeypatch):
    _target(write_toml)
    venv = _venv(tmp_path)
    write_fingerprint(
        venv,
        {
            "schema": REQUIREMENTS_SCHEMA,
            "target": "alpha",
            "python": "3.11.9",
            "requirements_sha256": _inputs_hash(tmp_path),
        },
    )
    _without_uv(monkeypatch)

    checks = check_installation(venv, root=tmp_path)

    assert any(
        check.status == OK and "installation inputs unchanged" in check.message
        for check in checks
    )
    assert not any("out of date" in check.message for check in checks)


def test_stale_fingerprint_fails_before_running_checks(
    tmp_path, write_toml, monkeypatch
):
    _target(write_toml)
    venv = _venv(tmp_path)
    write_fingerprint(
        venv,
        {
            "schema": REQUIREMENTS_SCHEMA,
            "target": "alpha",
            "python": "3.11.9",
            "requirements_sha256": "stale",
        },
    )
    _without_uv(monkeypatch)

    checks = check_installation(venv, root=tmp_path)

    assert [check.status for check in checks[:3]] == [OK, OK, FAIL]
    assert "out of date" in checks[2].message
    assert any(
        check.status == WARN and "uv missing" in check.message for check in checks
    )


def test_fingerprint_from_an_older_input_mode_asks_for_a_reinstall(
    tmp_path, write_toml, monkeypatch
):
    _target(write_toml)
    venv = _venv(tmp_path)
    recorded = {
        "target": "alpha",
        "python": "3.11.9",
        "requirements_sha256": "written by an older rpent-install",
    }
    _without_uv(monkeypatch)

    older = REQUIREMENTS_SCHEMA - 1
    for schema, label in ((older, str(older)), (None, "unknown")):
        fingerprint = dict(recorded)
        if schema is not None:
            fingerprint["schema"] = schema
        write_fingerprint(venv, fingerprint)

        checks = check_installation(venv, root=tmp_path)

        assert any(
            check.status == FAIL and f"input mode {label}" in check.message
            for check in checks
        )
        # The hash was recorded by a different input mode, so comparing it
        # would misreport drifted inputs instead of the required reinstall.
        assert not any("out of date" in check.message for check in checks)


def test_lock_edited_after_install_makes_the_environment_stale(
    tmp_path, write_toml, monkeypatch
):
    _target(write_toml, lock="installs/locks/alpha.lock")
    lock = write_toml("installs/locks/alpha.lock", "packaging==24.0")
    venv = _venv(tmp_path)
    write_fingerprint(
        venv,
        {
            "schema": REQUIREMENTS_SCHEMA,
            "target": "alpha",
            "python": "3.11.9",
            "requirements_sha256": _inputs_hash(tmp_path),
        },
    )
    _without_uv(monkeypatch)

    checks = check_installation(venv, root=tmp_path)
    assert any(
        check.status == OK and "installation inputs unchanged" in check.message
        for check in checks
    )

    # The target did not change, so only the lock hash can notice this.
    lock.write_text("packaging==25.0\n", encoding="utf-8")
    checks = check_installation(venv, root=tmp_path)

    assert any(
        check.status == FAIL and "out of date" in check.message for check in checks
    )


def test_target_name_overrides_the_fingerprint(tmp_path, write_toml, monkeypatch):
    _target(write_toml)
    venv = _venv(tmp_path)
    write_fingerprint(
        venv,
        {
            "schema": REQUIREMENTS_SCHEMA,
            "target": "alpha",
            "python": "3.11.9",
            "requirements_sha256": _inputs_hash(tmp_path),
        },
    )
    _without_uv(monkeypatch)

    checks = check_installation(venv, target_name="missing", root=tmp_path)

    assert any(
        check.status == FAIL and "cannot resolve target 'missing'" in check.message
        for check in checks
    )


def test_fingerprint_identity_is_reported(tmp_path, write_toml, monkeypatch):
    _target(write_toml)
    venv = _venv(tmp_path)
    fingerprint = {
        "schema": REQUIREMENTS_SCHEMA,
        "target": "alpha",
        "python": "3.11.9",
        "requirements_sha256": _inputs_hash(tmp_path),
    }
    write_fingerprint(venv, fingerprint)
    _without_uv(monkeypatch)

    checks = check_installation(venv, root=tmp_path)

    assert f"fingerprint sha256: {fingerprint_sha256(fingerprint)}" in {
        check.message for check in checks
    }


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
