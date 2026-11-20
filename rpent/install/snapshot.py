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

"""Record which installation produced a run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rpent.evaluation.result import write_json_atomic
from rpent.install.fingerprint import (
    current_venv,
    fingerprint_sha256,
    read_fingerprint,
)

RUN_MANIFEST_NAME = "run.json"


def installation_snapshot(venv: Path | None = None) -> dict[str, Any]:
    """Return the installation identity recorded in a run manifest.

    A run points at the installation that produced it instead of copying the
    fingerprint: the environment name and the fingerprint hash are enough to
    find that environment again. A checkout that was not installed through
    ``rpent-install`` records ``None`` for both.
    """
    active = Path(venv).resolve() if venv is not None else current_venv()
    fingerprint = read_fingerprint(active) if active is not None else None
    if fingerprint is None:
        return {"environment": None, "install_sha256": None}
    return {
        "environment": fingerprint.get("environment"),
        "install_sha256": fingerprint_sha256(fingerprint),
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
