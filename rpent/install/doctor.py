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
    runtime_platform,
)
from rpent.install.installer import (
    find_uv,
    probe_source,
    profile_resolution,
    venv_python,
)
from rpent.install.requirements import (
    REQUIREMENTS_SCHEMA,
    read_core_dependencies,
    requirements_sha256,
)
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
    profile_name: str | None = None,
    endpoints: dict[str, str] | None = None,
    root: Path | None = None,
) -> list[Check]:
    """Return diagnostic results for the environment in ``venv``."""
    repo_root = (root or get_repo_root()).resolve()
    venv = Path(venv).resolve()
    endpoints = endpoints or {}
    checks: list[Check] = []
    fingerprint = read_fingerprint(venv)
    if fingerprint is None:
        return [
            Check(
                FAIL,
                f"{venv} has no {FINGERPRINT_NAME}; "
                f"install it with `rpent-install install <profile> --venv {venv}`",
            )
        ]
    name = profile_name or fingerprint.get("profile")
    if name is None:
        return [*checks, Check(FAIL, "fingerprint records no profile")]
    checks.append(Check(OK, f"profile: {name}"))
    checks.append(Check(OK, f"installed at: {fingerprint.get('installed_at', '?')}"))
    try:
        resolution = profile_resolution(str(name), discover(repo_root), root=repo_root)
    except (InstallError, ValueError) as exc:
        checks.append(Check(FAIL, f"cannot resolve profile {name!r}: {exc}"))
        return checks
    if not resolution.ok:
        checks.append(Check(FAIL, "\n".join(resolution.errors)))
        return checks
    profile = resolution.profile
    core = read_core_dependencies(repo_root) if profile.core else ()
    expected_requirements = requirements_sha256(
        resolution,
        root=repo_root,
        core_dependencies=core,
    )
    recorded_schema = fingerprint.get("schema")
    if recorded_schema != REQUIREMENTS_SCHEMA:
        # `rpent-install` hashes a different set of inputs now, so the recorded
        # hash cannot be compared. Say so instead of reporting drifted inputs.
        interpreted = "unknown" if recorded_schema is None else recorded_schema
        checks.append(
            Check(
                FAIL,
                "fingerprint records installation input mode "
                f"{interpreted}, current is {REQUIREMENTS_SCHEMA}; rerun "
                f"`rpent-install install {name} --venv {venv}` to record the "
                "current inputs",
            )
        )
    elif fingerprint.get("requirements_sha256") != expected_requirements:
        checks.append(
            Check(
                FAIL,
                "environment is out of date with its recorded inputs (manifests, "
                f"lock, overrides, or [tool.uv]); rerun "
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
    expected_python = profile.python
    if not str(fingerprint.get("python", "")).startswith(expected_python + "."):
        checks.append(
            Check(
                FAIL,
                f"profile {profile.name!r} requires Python {expected_python}, "
                f"found {fingerprint.get('python', '?')}",
            )
        )
    current_platform = runtime_platform()
    if profile.platform != current_platform:
        checks.append(
            Check(
                FAIL,
                f"profile {profile.name!r} targets {profile.platform}, "
                f"this host is {current_platform}",
            )
        )
    else:
        checks.append(Check(OK, f"platform: {current_platform}"))

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
    for component in resolution.main_installed().values():
        probe = component.component.probe
        result = _run(
            [str(python), "-c", probe_source(probe)],
            env=environment,
        )
        if result.returncode != 0:
            checks.append(
                Check(
                    FAIL,
                    f"component {component.name!r} is not importable: "
                    f"{result.stderr.strip().splitlines()[-1] if result.stderr.strip() else probe}",
                )
            )
        else:
            checks.append(Check(OK, f"probe {component.name}: import {probe}"))

    for component in resolution.components.values():
        if component.placement != "remote" or component.component.is_deps:
            continue
        name = component.name
        endpoint = _endpoint_value(name, endpoints)
        if endpoint is None:
            checks.append(
                Check(
                    WARN,
                    f"remote component {name!r} has no endpoint; pass "
                    f"`--endpoint {name}=host:port` or set "
                    f"RPENT_{name.upper().replace('-', '_')}_ENDPOINT",
                )
            )
            continue
        problem = _probe_endpoint(endpoint)
        checks.append(
            Check(FAIL if problem else OK, problem or f"endpoint {name}: {endpoint}")
        )
    checks.append(Check(OK, f"fingerprint: {venv / FINGERPRINT_NAME}"))
    checks.append(Check(OK, f"fingerprint sha256: {fingerprint_sha256(fingerprint)}"))
    return checks
