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

"""Diagnose an installed environment against its recorded installation inputs."""

from __future__ import annotations

import os
import socket
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    FINGERPRINT_NAME,
    fingerprint_sha256,
    freeze_sha256,
    read_fingerprint,
)
from rpent.install.installer import (
    find_uv,
    probe_source,
    target_resolution,
    venv_python,
)
from rpent.install.requirements import (
    INPUT_SCHEMA,
    read_core_dependencies,
    requirements_sha256,
)
from rpent.install.resolve import python_accepted
from rpent.utils.config import get_repo_root

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class Check:
    """One diagnostic line."""

    status: str
    message: str


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


def _endpoint_value(name: str, endpoints: dict[str, str]) -> str | None:
    if name in endpoints:
        return endpoints[name]
    value = os.environ.get(f"RPENT_{name.upper().replace('-', '_')}_ENDPOINT")
    return value or None


def _endpoint_address(endpoint: str) -> tuple[str, int] | None:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.hostname is None:
        parsed = urllib.parse.urlsplit(f"//{endpoint}")
    if parsed.hostname is None:
        return None
    if parsed.port is not None:
        return parsed.hostname, parsed.port
    return None


def _probe_endpoint(endpoint: str) -> str | None:
    address = _endpoint_address(endpoint)
    if address is None:
        return f"cannot parse endpoint {endpoint!r}; expected host:port or a URL"
    try:
        with socket.create_connection(address, timeout=5):
            return None
    except OSError as exc:
        return f"endpoint {endpoint!r} is not reachable: {exc}"


def check_installation(
    venv: Path,
    *,
    target_name: str | None = None,
    endpoints: dict[str, str] | None = None,
    root: Path | None = None,
) -> list[Check]:
    """Return diagnostic results for the environment in ``venv``."""
    repo_root = (root or get_repo_root()).resolve()
    venv = Path(venv).resolve()
    endpoints = endpoints or {}
    checks: list[Check] = [Check(OK, f"venv: {venv}")]
    fingerprint = read_fingerprint(venv)
    if fingerprint is None:
        return [
            *checks,
            Check(
                FAIL,
                f"no {FINGERPRINT_NAME} in {venv}; "
                f"install it with `rpent-install install <target> --venv {venv}`",
            ),
        ]
    recorded_target = fingerprint.get("target")
    name = target_name or recorded_target
    if name is None:
        return [*checks, Check(FAIL, "fingerprint records no target")]
    checks.append(Check(OK, f"target: {name}"))
    if target_name is not None and target_name != recorded_target:
        recorded_label = "none" if recorded_target is None else repr(recorded_target)
        checks.append(
            Check(
                WARN,
                f"--target {target_name!r} overrides the target recorded in the "
                f"fingerprint ({recorded_label})",
            )
        )
    checks.append(Check(OK, f"installed at: {fingerprint.get('installed_at', '?')}"))
    catalog = discover(repo_root)
    try:
        resolution = target_resolution(str(name), catalog, root=repo_root)
    except (InstallError, ValueError) as exc:
        checks.append(Check(FAIL, f"cannot resolve target {name!r}: {exc}"))
        return checks
    if not resolution.ok:
        checks.append(Check(FAIL, "\n".join(resolution.errors)))
        return checks
    target = resolution.target
    core = read_core_dependencies(repo_root) if target.core else ()
    expected_requirements = requirements_sha256(
        resolution,
        root=repo_root,
        core_dependencies=core,
    )
    recorded_schema = fingerprint.get("schema")
    if recorded_schema != INPUT_SCHEMA:
        # `rpent-install` hashes a different set of inputs now, so the recorded
        # hash cannot be compared. Say so instead of reporting drifted inputs.
        interpreted = "unknown" if recorded_schema is None else recorded_schema
        checks.append(
            Check(
                FAIL,
                "fingerprint records installation input mode "
                f"{interpreted}, current is {INPUT_SCHEMA}; rerun "
                f"`rpent-install install {name} --venv {venv}` to record the "
                "current inputs",
            )
        )
    elif fingerprint.get("requirements_sha256") != expected_requirements:
        checks.append(
            Check(
                FAIL,
                "environment is out of date with its recorded inputs (manifests, "
                f"overrides, or [tool.uv]); rerun "
                f"`rpent-install install {name} --venv {venv}`",
            )
        )
    else:
        checks.append(Check(OK, "installation inputs unchanged"))

    python = venv_python(venv)
    if not python.exists():
        checks.append(Check(FAIL, f"no Python interpreter in {venv}"))
        return checks
    checks.append(Check(OK, f"python: {fingerprint.get('python', '?')}"))
    installed_python = str(fingerprint.get("python", ""))
    if not installed_python or not python_accepted(resolution, installed_python):
        ranges = "; ".join(
            f"{name}: {component.python}"
            for name, component in sorted(resolution.components.items())
            if component.python is not None
        )
        checks.append(
            Check(
                FAIL,
                f"the components of target {target.name!r} do not accept the "
                f"installed Python {fingerprint.get('python', '?')}"
                + (f" ({ranges})" if ranges else ""),
            )
        )
    checks.append(Check(OK, f"platform: {resolution.platform}"))

    try:
        uv = find_uv()
    except InstallError as exc:
        checks.append(Check(WARN, str(exc)))
        uv = None
    if uv is not None:
        frozen = _run([uv, "pip", "freeze", "--python", str(python)])
        if frozen.returncode != 0:
            checks.append(Check(FAIL, f"uv pip freeze failed: {frozen.stderr.strip()}"))
        elif freeze_sha256(frozen.stdout) != fingerprint.get("freeze_sha256"):
            checks.append(
                Check(
                    FAIL,
                    "installed packages changed since the fingerprint was written; "
                    f"rerun `rpent-install install {name} --venv {venv}`",
                )
            )
        else:
            checks.append(Check(OK, "installed package set matches the fingerprint"))
        checked = _run([uv, "pip", "check", "--python", str(python)])
        if checked.returncode != 0:
            checks.append(Check(FAIL, f"uv pip check failed: {checked.stdout.strip()}"))
        else:
            checks.append(Check(OK, "uv pip check"))

    environment = {**os.environ, "PYTHONPATH": str(repo_root)}
    for name, component in sorted(resolution.components.items()):
        probe = component.probe
        result = _run(
            [str(python), "-c", probe_source(probe)],
            env=environment,
        )
        if result.returncode != 0:
            detail = (
                result.stderr.strip().splitlines()[-1]
                if result.stderr.strip()
                else probe
            )
            checks.append(
                Check(FAIL, f"component {name!r} is not importable: {detail}")
            )
        else:
            checks.append(Check(OK, f"probe {name}: import {probe}"))

    # Services deployed as their own target are reached by endpoint. The
    # installation no longer records which components run elsewhere, so probe
    # every endpoint the caller passes and every environment variable that is
    # set for a known component.
    configured = dict(endpoints)
    for component_name in catalog.components:
        value = _endpoint_value(component_name, {})
        if value is not None:
            configured.setdefault(component_name, value)
    for component_name, endpoint in sorted(configured.items()):
        problem = _probe_endpoint(endpoint)
        checks.append(
            Check(
                FAIL if problem else OK,
                problem or f"endpoint {component_name}: {endpoint}",
            )
        )
    checks.append(Check(OK, f"fingerprint: {venv / FINGERPRINT_NAME}"))
    checks.append(Check(OK, f"fingerprint sha256: {fingerprint_sha256(fingerprint)}"))
    return checks
