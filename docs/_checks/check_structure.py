#!/usr/bin/env python3
"""Check structural conventions that a Sphinx build cannot see.

The documentation build catches broken references and malformed markup, but not
a page that lost its opening header or a numbered procedure whose headings no
longer match the step list. Run this from ``docs``::

    python3 _checks/check_structure.py

It reports, for both language trees:

* A page with two or more H2 sections must declare a ``page-head`` with all
  four options.
* A page with three or more H2 sections must carry a page map
  (``**Page map:**`` or ``**本文结构：**``).
* A page must not exceed 13 H2 sections; setup details belong in H3 sections
  under the step they support.
* Numbered H2 headings must run ``1..n`` without gaps or repeats.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
TREES = ("source-en", "source-zh")
PAGE_HEAD_OPTIONS = ("for", "outcome", "read-when", "skip-when")
UNDERLINE = re.compile(r"^([=\-~^])\1{2,}\s*$")
NUMBERED = re.compile(r"^(\d+)\.\s")
MAP_MARKERS = ("**Page map:**", "**本文结构：**")
MAX_H2 = 13
SKIP_NAMES = {
    "index.rst",
    "performance.rst",
    "time-token-costs.rst",
    "so101.rst",
    "contributing.rst",
}


def headings(lines: list[str]) -> list[tuple[str, str]]:
    """Return (title, underline character) pairs, ignoring literal blocks."""
    found: list[tuple[str, str]] = []
    literal_indent: int | None = None
    for index, line in enumerate(lines[:-1]):
        if literal_indent is not None:
            if not line.strip():
                continue
            if len(line) - len(line.lstrip()) > literal_indent:
                continue
            literal_indent = None
        stripped = line.strip()
        if stripped.startswith(".. code-block::") or stripped == "::":
            literal_indent = len(line) - len(line.lstrip())
            continue
        nxt = lines[index + 1]
        if stripped and UNDERLINE.match(nxt):
            found.append((stripped, nxt[0]))
    return found


def check_page(path: Path) -> list[str]:
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return problems
    h2 = [title for title, char in headings(lines) if char == "-"]
    text = "\n".join(lines)

    if len(h2) >= 2:
        if ".. page-head::" not in text:
            problems.append("missing page-head")
        else:
            block = text.split(".. page-head::", 1)[1].split("\n\n", 1)[0]
            for option in PAGE_HEAD_OPTIONS:
                if f"   :{option}:" not in block:
                    problems.append(f"page-head missing :{option}:")

    if len(h2) >= 3 and not any(marker in text for marker in MAP_MARKERS):
        problems.append("missing page map")

    if len(h2) > MAX_H2:
        problems.append(
            f"{len(h2)} H2 sections (limit {MAX_H2}); group setup detail as H3 "
            "or split the page"
        )

    numbered = [int(m.group(1)) for title in h2 if (m := NUMBERED.match(title))]
    if numbered and numbered != list(range(1, len(numbered) + 1)):
        problems.append(
            "numbered H2 headings are not sequential: "
            + ", ".join(str(number) for number in numbered)
        )
    return problems


def main() -> int:
    failures = 0
    for tree in TREES:
        for path in sorted((DOCS / tree / "rst_source").rglob("*.rst")):
            if path.name.startswith("_") or path.name in SKIP_NAMES:
                continue
            problems = check_page(path)
            for problem in problems:
                print(f"{path.relative_to(DOCS)}: {problem}")
            failures += len(problems)
    if failures:
        print(f"\n{failures} structural problem(s) found.")
        return 1
    print("Documentation structure is consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
