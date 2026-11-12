#!/usr/bin/env python3
"""对比中英页面的结构指标，找出明显不同步的页面。

用法（在 rpent 仓库根目录）：
    python3 /Users/qurakchin/Works/rpent_docs_revamp/audit/structure.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
ZH = REPO / "docs/source-zh/rst_source"
EN = REPO / "docs/source-en/rst_source"


def metrics(path: pathlib.Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    headings = []
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and re.fullmatch(r"[=\-~^\"'`#*+]{3,}", lines[i + 1].strip()):
            headings.append((line.strip(), len(lines[i + 1].strip())))
    return {
        "lines": len(lines),
        "headings": headings,
        "code_blocks": text.count("code-block::"),
        "list_tables": text.count("list-table::"),
        "images": text.count("figure::") + text.count("image::"),
        "refs": len(re.findall(r":(?:doc|ref):`", text)),
        "raw_html": text.count("raw:: html"),
    }


def main():
    rows = []
    for zh in sorted(ZH.rglob("*.rst")):
        en = EN / zh.relative_to(ZH)
        if not en.exists():
            rows.append((str(zh.relative_to(ZH)), "缺少英文", None, None))
            continue
        a, b = metrics(zh), metrics(en)
        diffs = []
        if len(a["headings"]) != len(b["headings"]):
            diffs.append(f"标题数 {len(a['headings'])}→{len(b['headings'])}")
        if abs(a["lines"] - b["lines"]) > max(15, 0.3 * a["lines"]):
            diffs.append(f"行数 {a['lines']}→{b['lines']}")
        for key in ("code_blocks", "list_tables", "images", "raw_html"):
            if a[key] != b[key]:
                diffs.append(f"{key} {a[key]}→{b[key]}")
        if diffs:
            rows.append((str(zh.relative_to(ZH)), "；".join(diffs), a, b))
    for row in rows:
        print(row[0], "|", row[1])
    print(f"\n共 {len(rows)} 篇结构存在差异（按标题数/行数/代码块/表格/图片判断）")


if __name__ == "__main__":
    main()
