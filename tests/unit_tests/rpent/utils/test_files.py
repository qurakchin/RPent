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

"""Contracts for atomic artifact writes."""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from rpent.utils.files import write_text_atomic


def test_concurrent_writers_do_not_share_a_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "shared.json"
    texts = [json.dumps({"writer": index}) + "\n" for index in range(8)]
    errors: list[BaseException] = []

    def write(index: int) -> None:
        try:
            for _ in range(20):
                write_text_atomic(target, texts[index])
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert target.read_text(encoding="utf-8") in texts
    assert not list(tmp_path.glob(".*.tmp"))


def test_failed_replace_keeps_the_previous_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.json"
    write_text_atomic(target, "old\n")

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(".*.tmp"))


def test_existing_mode_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "run.log"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o640)

    write_text_atomic(target, "new\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_replacing_a_symlink_writes_a_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("original\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    write_text_atomic(link, "updated\n")

    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == "updated\n"
    assert target.read_text(encoding="utf-8") == "original\n"
