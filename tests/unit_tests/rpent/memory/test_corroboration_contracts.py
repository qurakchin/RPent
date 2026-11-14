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

"""Merge-time handling of corroboration records."""

from __future__ import annotations

from pathlib import Path

from rpent.memory import MemoryManager
from rpent.memory.manager import _split_frontmatter


def _published(root: Path, confidence: str, cells: list[str]) -> Path:
    path = root / "global" / "strategy.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = "\n".join(f"    - {cell}" for cell in cells)
    path.write_text(
        "---\n"
        "scope: global\n"
        "kind: strategy\n"
        "title: Strategy\n"
        "applies_when: always\n"
        f"confidence: {confidence}\n"
        "evidence:\n"
        "  cells:\n"
        f"{evidence}\n"
        "  attempts: 1\n"
        "---\n"
        "Body.\n"
    )
    return path


def _manager(root: Path) -> MemoryManager:
    return MemoryManager(root, memory_access="inbox_write", inbox_cell_tag="cell_a")


def test_confirmed_corroboration_adds_a_cell_and_recomputes_confidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "memory"
    published = _published(root, "single-shot", ["other_cell"])
    manager = _manager(root)
    manager.append_corroboration(memory_id="strategy", outcome="confirmed")

    result = manager.merge_memory(
        cell_tag="cell_a", run_state_dir=tmp_path, solved=False
    )

    assert result["corroborations"] == 1
    metadata, _ = _split_frontmatter(published)
    assert metadata["evidence"]["cells"] == ["cell_a", "other_cell"]
    assert metadata["evidence"]["attempts"] == 2
    assert metadata["confidence"] == "probable"
    assert not (root / "_internal" / "inbox" / "cell_a").exists()


def test_contradicted_corroboration_records_the_cell_and_lowers_confidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "memory"
    published = _published(root, "verified", ["a_1", "a_2", "b_1"])
    manager = _manager(root)
    manager.append_corroboration(memory_id="strategy", outcome="contradicted")

    result = manager.merge_memory(
        cell_tag="cell_a", run_state_dir=tmp_path, solved=False
    )

    assert result["corroborations"] == 1
    metadata, _ = _split_frontmatter(published)
    assert metadata["confidence"] == "probable"
    assert metadata["evidence"]["contradicted_by"] == ["cell_a"]


def test_unknown_memory_id_is_skipped_not_invented(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _published(root, "single-shot", ["other_cell"])
    manager = _manager(root)
    manager.append_corroboration(memory_id="missing_note", outcome="confirmed")

    result = manager.merge_memory(
        cell_tag="cell_a", run_state_dir=tmp_path, solved=False
    )

    assert result["corroborations"] == 0
    assert any("missing_note" in item for item in result["skipped"])
    assert not (root / "global" / "missing_note.md").exists()
