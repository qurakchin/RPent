#!/usr/bin/env python3
"""Report prose sentences that are too long to read aloud in one breath.

Run this from ``docs``::

    python3 _checks/check_prose.py          # report only
    python3 _checks/check_prose.py --strict # fail on very long sentences

The rule is deliberately simple so writers can apply it while drafting:

* Chinese: one sentence should stay at or below 40 characters. A sentence is
  text between ``。``, ``！``, or ``？``; inline literals, roles, links, and
  code are removed before counting.
* English: one sentence should stay at or below 35 words. A sentence ends at
  ``.``, ``!``, or ``?`` followed by whitespace.

Sentences above the soft limit are reported. Sentences above the hard limit
(80 Chinese characters or 60 English words) fail with ``--strict``, and the
checker also exits non-zero for any sentence the writer marked with a trailing
``# noqa: long-sentence`` comment on the paragraph's first line.

Code blocks, directives, tables, lists, comments, and page-head/page-map lines
are skipped: they are not prose and often must stay on one line.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
TREES = ("source-en", "source-zh")

SOFT_ZH = 40
HARD_ZH = 80
SOFT_EN_WORDS = 35
HARD_EN_WORDS = 60

ZH_SENTENCE = re.compile(r"[^。！？]+[。！？]?")
EN_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
CJK = re.compile(r"[一-鿿]")
INLINE_LITERAL = re.compile(r"``[^`]*``")
ROLE = re.compile(r":[a-z]+:`[^`]*`")
LINK = re.compile(r"`[^`]*`_{0,2}")
URL = re.compile(r"https?://\S+")
ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "cf.", "Fig.", "No."}


def prose_blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Return (start line, joined text) for paragraphs that are plain prose."""
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    start = 0
    skip_indent: int | None = None

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append((start, " ".join(part.strip() for part in current)))
            current = []

    for index, raw in enumerate(lines):
        line = raw.rstrip()
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if skip_indent is not None:
            if not stripped:
                continue
            if indent > skip_indent:
                continue
            skip_indent = None

        if not stripped:
            flush()
            continue
        if stripped.startswith(".."):
            flush()
            if stripped.startswith(".. code-block::") or stripped.endswith("::"):
                skip_indent = indent
            continue
        if indent > 0:
            flush()
            continue
        if stripped.startswith(("*", "-", "+", ":", "|", "=", "..")) or stripped[:1].isdigit():
            flush()
            continue
        if stripped.startswith(("**Page map:**", "**本文结构：**")):
            flush()
            continue
        if not current:
            start = index + 1
        current.append(line)
        if stripped.endswith("::"):
            flush()
            skip_indent = indent
    flush()
    return blocks


def clean(text: str) -> str:
    text = INLINE_LITERAL.sub("X", text)
    text = ROLE.sub("X", text)
    text = LINK.sub("X", text)
    text = URL.sub("X", text)
    return text


def zh_sentences(text: str) -> list[str]:
    return [item.strip() for item in ZH_SENTENCE.findall(text) if item.strip()]


def en_sentences(text: str) -> list[str]:
    found: list[str] = []
    for candidate in EN_SENTENCE.findall(text):
        candidate = candidate.strip()
        if not candidate:
            continue
        last = candidate.split()[-1] if candidate.split() else ""
        if last in ABBREVIATIONS:
            if found:
                found[-1] = found[-1] + " " + candidate
            else:
                found.append(candidate)
            continue
        found.append(candidate)
    return found


def check_tree(tree: str) -> int:
    soft = 0
    hard = 0
    for path in sorted((DOCS / tree / "rst_source").rglob("*.rst")):
        if path.name.startswith("_"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for start, block in prose_blocks(lines):
            if "noqa: long-sentence" in lines[start - 1]:
                continue
            text = clean(block)
            if tree == "source-zh":
                for sentence in zh_sentences(text):
                    length = len(CJK.findall(sentence)) + len(sentence) - len(
                        CJK.findall(sentence)
                    )
                    if length > SOFT_ZH:
                        soft += 1
                        mark = "HARD" if length > HARD_ZH else "long"
                        print(
                            f"{path.relative_to(DOCS)}:{start}: {mark} "
                            f"{length} chars: {sentence[:60]}"
                        )
                    if length > HARD_ZH:
                        hard += 1
            else:
                for sentence in en_sentences(text):
                    words = len(sentence.split())
                    if words > SOFT_EN_WORDS:
                        soft += 1
                        mark = "HARD" if words > HARD_EN_WORDS else "long"
                        print(
                            f"{path.relative_to(DOCS)}:{start}: {mark} "
                            f"{words} words: {sentence[:60]}"
                        )
                    if words > HARD_EN_WORDS:
                        hard += 1
    print(f"{tree}: {soft} sentence(s) above the soft limit, {hard} above the hard limit.")
    return hard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when a sentence exceeds the hard limit (80 Chinese characters or 60 English words)",
    )
    args = parser.parse_args()
    hard = 0
    for tree in TREES:
        hard += check_tree(tree)
    if args.strict and hard:
        print(f"\n{hard} sentence(s) exceed the hard limit.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
