#!/usr/bin/env python3
"""审计 rpent 文档中可自动核对的事实。

聚焦高信噪比项：
- code-block 中 rpent 系命令行使用的 ``--flag`` 是否在源码中出现；
- 内联 ``--flag`` 在同一段落提到 rpent 时的校验；
- ``.[extra]`` 是否为 pyproject 定义的 extra；
- 内联反引号中的 ``robots/...``、``rpent/...``、``docs/...`` 路径是否存在。

用法（在 rpent 仓库根目录）：
    python3 /Users/qurakchin/Works/rpent_docs_revamp/audit/scan.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
RPENT_CMD = re.compile(r"^(rpent|rpent-check-llm|rpent-memory|rpent-flywheel|liberopro-download-assets)\b")
PY_MODULE_CMD = re.compile(r"^python(3(\.\d+)?)?\s+-m\s+(robots\.[\w.]+|rpent\.[\w.]+)")
PATH_LITERAL = re.compile(r"^(?:robots|rpent|docs|tests|requirements|calibration_tools)/[\w./-]+\.(?:py|rst|md|json|yaml|yml|txt|sh)$")


def source_flags() -> set[str]:
    flags = set()
    for f in REPO.rglob("*.py"):
        if any(p in f.parts for p in (".venv", "build", ".docs-venv")):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        flags.update(re.findall(r'"(--[a-z][a-z0-9-]*)"', txt))
        flags.update(re.findall(r"'(--[a-z][a-z0-9-]*)'", txt))
        # add_argument("-x", ...) 短选项
        flags.update(re.findall(r'add_argument\("(-[a-zA-Z])"', txt))
    return flags


def extras() -> set[str]:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^\[project\.optional-dependencies\]\s*$", text, re.M)
    if not m:
        return set()
    rest = text[m.end():]
    nxt = re.search(r"^\[", rest, re.M)
    if nxt:
        rest = rest[: nxt.start()]
    return set(re.findall(r"^([a-z0-9-]+)\s*=\s*\[", rest, re.M))


def check_flags(cmd_text: str, f: pathlib.Path, line_no: int, source: set[str]):
    for m in re.finditer(r"(?<![\w-])(--[a-z][a-z0-9-]*)", cmd_text):
        flag = m.group(1)
        if flag in ("--help", "--version"):
            continue
        if flag not in source:
            yield (f, line_no, f"rpent 参数 {flag} 在源码中未出现")


def main():
    src = source_flags()
    ex = extras()
    problems = []

    for tree in ("docs/source-en/rst_source", "docs/source-zh/rst_source"):
        for f in (REPO / tree).rglob("*.rst"):
            lines = f.read_text(encoding="utf-8").splitlines()
            in_code = False
            code_indent = 0
            code_is_rpent = False
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if not in_code:
                    if re.match(r"\.\. code-block::", stripped):
                        in_code = True
                        code_indent = len(line) - len(line.lstrip())
                        code_is_rpent = False
                        continue
                    # 内联检查
                    for m in re.finditer(r"``([^`]+)``", line):
                        span = m.group(1).strip()
                        if span.startswith(".") and "[" in span:
                            for e in re.findall(r"[a-z0-9-]+", span):
                                if e and e not in ex and e not in ("",):
                                    problems.append((f, i, f"extra [{e}] 未在 pyproject 定义"))
                        if PATH_LITERAL.match(span) and not (REPO / span).exists():
                            problems.append((f, i, f"路径 {span} 不存在"))
                    if "rpent" in line:
                        problems.extend(check_flags(line, f, i, src))
                    continue
                # 代码块内
                if stripped == "":
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= code_indent and not stripped.startswith("#"):
                    in_code = False
                    continue
                cmd = stripped.lstrip("$ ").strip()
                if RPENT_CMD.match(cmd) or PY_MODULE_CMD.match(cmd):
                    code_is_rpent = True
                elif cmd.startswith("-") or cmd.startswith("--"):
                    pass  # 续行
                else:
                    code_is_rpent = False
                    code_is_rpent = bool(re.search(r"\brpent\b", cmd) and " --" in cmd)
                if code_is_rpent:
                    problems.extend(check_flags(cmd, f, i, src))

    seen = set()
    for f, line_no, msg in problems:
        key = (f.relative_to(REPO), msg)
        if key in seen:
            continue
        seen.add(key)
        print(f"{f.relative_to(REPO)}:{line_no}: {msg}")
    print(f"\n共 {len(seen)} 条待核对")


if __name__ == "__main__":
    main()
