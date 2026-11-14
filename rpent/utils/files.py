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
import secrets
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _create_temporary(path: Path) -> tuple[int, Path]:
    """Create a unique sibling file whose mode the process umask masks.

    :func:`tempfile.mkstemp` always creates ``0600``, which would make run
    artifacts ignore the umask that governs the rest of their directory.
    ``os.open`` applies the umask to ``0o666`` instead, and ``O_EXCL`` keeps
    concurrent writers on distinct names.
    """
    for _ in range(100):
        candidate = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o666,
            )
        except FileExistsError:
            continue
        return descriptor, candidate
    raise FileExistsError(f"could not create a temporary file next to {path}")


def write_text_atomic(destination: Path | str, text: str) -> Path:
    """Write ``text`` so readers never observe a partial file.

    The text goes to a unique sibling temporary file that is flushed to disk and
    moved into place with :func:`os.replace`. Concurrent writers therefore use
    distinct temporary files, and a crash mid-write leaves the previous file
    intact. The replacement preserves an existing file's mode; a new file takes
    ``0o666`` masked by the process umask, like a regular open. Replacing a
    symlink replaces the link itself, as :func:`os.replace` does.
    """
    path = Path(destination)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None
    descriptor, temporary = _create_temporary(path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            if mode is not None:
                os.fchmod(handle.fileno(), mode)
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
