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

"""Memory family behavior over a real temporary corpus."""

from __future__ import annotations

import json
from pathlib import Path

from rpent.memory import MemoryManager
from rpent.tools.memory_tools import MemoryTools


def _leaf(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "scope: global\n"
        "kind: strategy\n"
        f"title: {title}\n"
        f"applies_when: {title}\n"
        "confidence: probable\n"
        "evidence:\n"
        "  cells: [other]\n"
        "  attempts: 1\n"
        "---\n"
        f"{body}\n"
    )


def _manager(root: Path, *, access: str = "inbox_write") -> MemoryManager:
    return MemoryManager(
        root,
        memory_access=access,
        inbox_cell_tag="cell_a" if access == "inbox_write" else None,
    )


def test_recall_ranks_matching_leaves_and_hides_unmatched(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    _leaf(
        root / "global" / "hammer.md",
        "Hammer grasp",
        "Grasp the hammer near the head.",
    )
    _leaf(root / "global" / "cup.md", "Cup lift", "Lift the cup vertically.")
    tools = MemoryTools(_manager(root, access="read_only"))

    result = tools.recall("hammer grasp")

    assert result.call_ok is True
    assert result.data["count"] == 1
    match = result.data["matches"][0]
    assert match["title"] == "Hammer grasp"
    assert match["scope"] == "global"
    assert match["score"] >= 2
    assert "hammer" in match["snippet"].lower()


def test_recall_searches_task_specific_and_audits_delivered_reads(
    tmp_path: Path,
) -> None:
    root = tmp_path / "memory"
    _leaf(root / "global" / "hammer.md", "Hammer grasp", "Grasp the hammer head.")
    directory = root / "task-specific"
    directory.mkdir(parents=True)
    (directory / "beat_block_hammer.json").write_text('{"task": "hammer"}')
    (directory / "cup_only.json").write_text('{"task": "cup"}')
    tools = MemoryTools(_manager(root, access="read_only"))

    result = tools.recall("hammer", scope="all")

    assert result.call_ok is True
    assert {match["scope"] for match in result.data["matches"]} == {
        "global",
        "task-specific",
    }
    audit = [
        json.loads(line)
        for line in (root / "_internal" / "audit" / "reads.jsonl")
        .read_text()
        .splitlines()
    ]
    assert {record["path"] for record in audit} == {
        "global/hammer.md",
        "task-specific/beat_block_hammer.json",
    }


def test_recall_rejects_an_empty_query(tmp_path: Path) -> None:
    tools = MemoryTools(_manager(tmp_path / "memory", access="read_only"))
    result = tools.recall("   ")

    assert result.call_ok is False
    assert result.error["code"] == "validation"
    assert result.no_execution is True


def test_remember_requires_scope_fields_and_writes_an_unpublished_draft(
    tmp_path: Path,
) -> None:
    root = tmp_path / "memory"
    tools = MemoryTools(_manager(root))

    missing = tools.remember(
        scope="global",
        body="Observation without a title.",
    )
    assert missing.call_ok is False
    assert missing.error["code"] == "validation"

    written = tools.remember(
        scope="global",
        kind="strategy",
        title="Approach from the free side",
        applies_when="both arms are free",
        body="Observed that approaching from the free side avoided collisions.",
    )
    assert written.call_ok is True
    draft = Path(written.data["draft"])
    assert draft.parent == root / "_internal" / "inbox" / "cell_a"
    assert draft.name.endswith("_draft.md")
    assert not list((root / "global").glob("*.md"))


def test_remember_is_refused_without_inbox_write_access(tmp_path: Path) -> None:
    tools = MemoryTools(_manager(tmp_path / "memory", access="read_only"))
    result = tools.remember(
        scope="global",
        kind="strategy",
        title="Title",
        applies_when="always",
        body="Body.",
    )

    assert result.call_ok is False
    assert result.error["code"] == "refused"
    assert result.no_execution is True


def test_memory_writes_are_exclusive_and_do_not_capture_state() -> None:
    assert MemoryTools.recall.readonly is True
    for write in (MemoryTools.remember, MemoryTools.corroborate):
        assert write.readonly is False
        assert write.captures_state is False


def test_corroborate_records_the_outcome_in_the_inbox(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    tools = MemoryTools(_manager(root))

    result = tools.corroborate(
        "hammer",
        outcome="confirmed",
        evidence="The grasp held through transport.",
    )
    assert result.call_ok is True
    path = Path(result.data["corroborations"])
    record = json.loads(path.read_text().splitlines()[0])
    assert record == {
        "cell": "cell_a",
        "evidence": {"note": "The grasp held through transport."},
        "memory_id": "hammer",
        "outcome": "confirmed",
    }
