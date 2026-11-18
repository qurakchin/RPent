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
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    FINGERPRINT_NAME,
    freeze_sha256,
    read_fingerprint,
    runtime_platform,
)
from rpent.install.installer import (
    find_uv,
    probe_source,
    repair_command,
    resolve_targets,
    venv_python,
)
from rpent.install.requirements import (
    REQUIREMENTS_SCHEMA,
    read_core_dependencies,
    requirements_sha256,
)
from rpent.install.resolve import python_errors
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


def check_installation(venv: Path, *, root: Path | None = None) -> list[Check]:
    """Return diagnostic results for the environment in ``venv``."""
    repo_root = (root or get_repo_root()).resolve()
    venv = Path(venv).resolve()
    checks: list[Check] = []
    fingerprint = read_fingerprint(venv)
    if fingerprint is None:
        return [
            Check(
                FAIL,
                f"{venv} has no {FINGERPRINT_NAME}; install it with "
                f"`rpent-install install <components> --venv {venv}`",
            )
        ]
    targets = fingerprint.get("targets")
    if not isinstance(targets, list) or not targets:
        return [
            Check(
                FAIL,
                "fingerprint records no target components; reinstall with "
                f"`rpent-install install <components> --venv {venv}`",
            )
        ]
    checks.append(Check(OK, f"targets: {', '.join(targets)}"))
    checks.append(Check(OK, f"installed at: {fingerprint.get('installed_at', '?')}"))
    try:
        catalog = discover(repo_root)
        resolution = resolve_targets(
            targets, catalog, root=repo_root, platform=runtime_platform()
        )
    except (InstallError, ValueError) as exc:
        checks.append(Check(FAIL, f"cannot resolve {' '.join(targets)!r}: {exc}"))
        return checks
    if not resolution.ok:
        checks.append(Check(FAIL, "\n".join(resolution.errors)))
        return checks
    core = read_core_dependencies(repo_root)
    expected_requirements = requirements_sha256(
        resolution, root=repo_root, core_dependencies=core
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
                f"`{repair_command(resolution)} --venv {venv}` to record the "
                "current inputs",
            )
        )
    elif fingerprint.get("requirements_sha256") != expected_requirements:
        checks.append(
            Check(
                FAIL,
                "environment is out of date with its recorded inputs (manifests, "
                f"overrides, or [tool.uv]); rerun "
                f"`{repair_command(resolution)} --venv {venv}`",
            )
        )
    else:
        checks.append(Check(OK, "installation inputs unchanged"))

    python = venv_python(venv)
    if not python.exists():
        checks.append(Check(FAIL, f"no Python interpreter in {venv}"))
        return checks
    checks.append(Check(OK, f"python: {fingerprint.get('python', '?')}"))
    unsupported = python_errors(
        str(fingerprint.get("python", "")),
        resolution.components.values(),
        owner=str(venv),
    )
    if unsupported:
        checks.append(Check(FAIL, "\n".join(unsupported)))
    checks.append(Check(OK, f"platform: {runtime_platform()}"))

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
                    f"rerun `{repair_command(resolution)} --venv {venv}`",
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
    for name, component in resolution.components.items():
        probe = component.probe
        result = _run(
            [str(python), "-c", probe_source(probe)],
            env=environment,
        )
        if result.returncode != 0:
            checks.append(
                Check(
                    FAIL,
                    f"component {name!r} is not importable: "
                    f"{result.stderr.strip().splitlines()[-1] if result.stderr.strip() else probe}",
                )
            )
        else:
            checks.append(Check(OK, f"probe {name}: import {probe}"))
    return checks


def inspect_installation(venv: Path) -> dict[str, Any] | None:
    """Return the stored fingerprint with its canonical hash, or ``None``."""
    from rpent.install.fingerprint import fingerprint_sha256

    fingerprint = read_fingerprint(venv)
    if fingerprint is None:
        return None
    return {
        "venv": str(Path(venv).resolve()),
        "sha256": fingerprint_sha256(fingerprint),
        "fingerprint": fingerprint,
    }
