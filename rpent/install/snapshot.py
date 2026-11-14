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

"""Expose the installation fingerprint through per-run artifacts."""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rpent.evaluation.result import write_json_atomic
from rpent.install.fingerprint import (
    current_venv,
    fingerprint_sha256,
    read_fingerprint,
    runtime_platform,
)

RUN_MANIFEST_NAME = "run.json"


def installation_snapshot(venv: Path | None = None) -> dict[str, Any]:
    """Return the current environment's installation identity.

    A source checkout that was not installed through ``rpent-env`` still gets a
    snapshot, but ``profile`` and ``install_sha256`` are ``None`` so a run can
    be traced to the environment that produced it.
    """
    active = Path(venv).resolve() if venv is not None else current_venv()
    fingerprint = read_fingerprint(active) if active is not None else None
    if fingerprint is None:
        return {
            "profile": None,
            "install_sha256": None,
            "python": platform.python_version(),
            "platform": runtime_platform(),
            "venv": str(active) if active is not None else None,
            "components": [],
        }
    return {
        "profile": fingerprint.get("profile"),
        "install_sha256": fingerprint_sha256(fingerprint),
        "python": fingerprint.get("python", platform.python_version()),
        "platform": fingerprint.get("platform", runtime_platform()),
        "venv": str(active),
        "components": sorted(fingerprint.get("components", {})),
        "source_commit": fingerprint.get("source_commit"),
        "source_dirty": fingerprint.get("source_dirty", False),
    }


def record_run_environment(
    output_dir: Path | str,
    *,
    venv: Path | None = None,
) -> Path:
    """Merge the environment snapshot into ``<output_dir>/run.json``.

    Existing keys are preserved so later manifest writers can add fields
    without this helper dropping them.
    """
    destination = Path(output_dir) / RUN_MANIFEST_NAME
    record: dict[str, Any] = {}
    if destination.is_file():
        try:
            record = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {}
    record.setdefault("schema", 1)
    record.setdefault(
        "started_at",
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    )
    record["environment"] = installation_snapshot(venv)
    return write_json_atomic(destination, record)
