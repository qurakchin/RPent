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

"""Memory family: search published memory, draft findings, corroborate claims.

Drafts and corroborations go through :class:`MemoryManager`, so the inbox
boundary and the merge-time confidence rules stay in one place.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Sequence

from pydantic import Field

from rpent.memory.manager import KINDS, MemoryManager
from rpent.tools.base import Tool, ToolResult, iter_tools, tool, tool_error
from rpent.tools.capabilities import Capabilities, ToolFamily


class MemoryTools(ToolFamily):
    """Recall, remember, and corroborate over the run's memory corpus."""

    name = "memory"

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def tools(
        self,
        capabilities: Capabilities | None = None,
        config: Any = None,
    ) -> Sequence[Tool]:
        return tuple(iter_tools(self))

    @tool(readonly=True)
    def recall(
        self,
        query: str,
        *,
        scope: Literal["all", "global", "task-family"] = "all",
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> ToolResult:
        """Search published memory for prior findings. Returns matching notes with confidence and paths; inspect a match before relying on it.

        Args:
            query: Words to look for in titles and note bodies.
            scope: Memory layer to search.
            limit: Maximum matches to return.
        """
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return tool_error("validation", "query must contain at least one word")
        scopes = ("global", "task-family") if scope == "all" else (scope,)
        matches: list[dict[str, Any]] = []
        for layer in scopes:
            directory = self._memory.root / layer
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                try:
                    resolved, metadata, body = self._memory.load_leaf(path)
                except (PermissionError, ValueError):
                    continue
                haystack = " ".join(
                    [
                        str(metadata.get("title", "")),
                        str(metadata.get("applies_when", "")),
                        body,
                    ]
                ).lower()
                score = sum(haystack.count(term) for term in terms)
                if score == 0:
                    continue
                matches.append(
                    {
                        "path": str(resolved),
                        "scope": metadata.get("scope", layer),
                        "title": metadata.get("title") or metadata.get("id"),
                        "confidence": metadata.get("confidence"),
                        "applies_when": metadata.get("applies_when"),
                        "snippet": body.strip()[:400],
                        "score": score,
                    }
                )
        matches.sort(key=lambda item: (-item["score"], item["path"]))
        return ToolResult(
            data={
                "query": query,
                "scope": scope,
                "count": min(len(matches), int(limit)),
                "matches": matches[: int(limit)],
            }
        )

    @tool(readonly=True)
    def remember(
        self,
        *,
        scope: Literal["global", "task-family"],
        body: str,
        title: str | None = None,
        kind: Literal["primitive", "perception", "strategy", "failure", "infra"]
        | None = None,
        applies_when: str | None = None,
        suite: str | None = None,
        regime: str | None = None,
        task_id: str | None = None,
        task_language: str | None = None,
        reason: str | None = None,
    ) -> ToolResult:
        """Draft a reusable finding into the current exploration cell's inbox. Drafts are not published until the cell merges; write only what the run actually observed.

        Args:
            scope: Global lesson or task-family note.
            body: Markdown body stating the observation and when it applies.
            title: Short global title; required for a global draft.
            kind: Global category.
            applies_when: Global applicability condition.
            suite: Task-family suite name.
            regime: Task-family regime name.
            task_id: Task-family task id.
            task_language: Task-family task instruction.
            reason: Why this finding is worth keeping.
        """
        if kind is not None and kind not in KINDS:
            return tool_error("validation", f"unknown memory kind: {kind}")
        metadata: dict[str, Any] = {"scope": scope, "confidence": "single-shot"}
        if scope == "global":
            metadata.update({"kind": kind, "title": title, "applies_when": applies_when})
        else:
            metadata.update(
                {
                    "suite": suite,
                    "regime": regime,
                    "task_id": task_id,
                    "task_language": task_language,
                }
            )
        if reason:
            metadata["reason"] = reason
        try:
            draft = self._memory.write_draft(metadata, body)
        except PermissionError as exc:
            return tool_error("refused", str(exc))
        except ValueError as exc:
            return tool_error("validation", str(exc))
        return ToolResult(
            data={
                "draft": str(draft),
                "memory_id": draft.stem.removesuffix("_draft"),
                "scope": scope,
                "notice": "Draft stored in this cell's inbox; it is not published yet.",
            }
        )

    @tool(readonly=True)
    def corroborate(
        self,
        memory_id: str,
        *,
        outcome: Literal["confirmed", "contradicted"],
        evidence: str | None = None,
    ) -> ToolResult:
        """Record whether this cell's run confirmed or contradicted a published memory. Merging updates its evidence and confidence.

        Args:
            memory_id: Published memory id, without the .md suffix.
            outcome: Whether the run confirmed or contradicted the claim.
            evidence: Concrete observation supporting the outcome.
        """
        try:
            path = self._memory.append_corroboration(
                memory_id=memory_id,
                outcome=outcome,
                evidence={"note": evidence} if evidence else None,
            )
        except PermissionError as exc:
            return tool_error("refused", str(exc))
        except ValueError as exc:
            return tool_error("validation", str(exc))
        return ToolResult(
            data={
                "recorded": True,
                "memory_id": memory_id,
                "outcome": outcome,
                "corroborations": str(path),
            }
        )


__all__ = ["MemoryTools"]
