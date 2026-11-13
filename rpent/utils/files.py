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

"""Filesystem helpers shared by run artifacts and prompt dumps."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def write_text_atomic(destination: Path | str, text: str) -> Path:
    """Write ``text`` so readers never observe a partial file.

    The text goes to a sibling temporary file that :func:`os.replace` moves into
    place, so a crash mid-write leaves the previous file intact.
    """
    path = Path(destination)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def write_json_atomic(
    destination: Path | str,
    record: Mapping[str, Any],
    *,
    ensure_ascii: bool = True,
) -> Path:
    """Write one JSON object atomically and return its destination path."""
    text = json.dumps(record, indent=2, ensure_ascii=ensure_ascii)
    return write_text_atomic(destination, text + "\n")
