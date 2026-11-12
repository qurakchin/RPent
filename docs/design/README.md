# Design documents

Status: current index. Baseline `7614ada`, last updated 2026-11-12.

This directory holds design rationale for the RPent refactor series. It is
plain Markdown, outside the Sphinx source trees: these documents explain why a
change is needed and how it will be accepted, while the user and developer
guides under `docs/source-en/` and `docs/source-zh/` describe current behavior.

## Reading order

Read the shared rules first, then the target architecture, then the topics:

1. [a_global](a_global.md) — terms, layers, rules R1–R12, acceptance and
   migration switches shared by every topic.
2. [a_summary](a_summary.md) — target architecture, module comparison,
   directory layout, and expected code size.
3. [a_0](a_0_建立文档纪律与评审闸门.md) — documentation discipline and review
   gates. This topic is implemented; section 9 maps each phase to its files.
4. [a_1](a_1_隔离组件依赖与安装.md) — component manifests, environment
   recipes, and install fingerprints.
5. [a_5](a_5_精简机器人接入.md) and [a_6](a_6_建立执行回执语义.md) — semantic
   environment contracts, adapters, and write receipts.
6. [a_3](a_3_抽出共享工具族.md) and [a_7](a_7_隔离任务真值.md) — shared tool
   families, independent tool evaluation, and truth isolation.
7. [a_2](a_2_拼装提示词.md), [a_4](a_4_统一代码策略调用.md), and
   [a_8](a_8_统一运行产物.md) — prompt assembly, code-policy calls, and run
   artifacts.
8. [a_9](a_9_建立验证护栏.md) — tests, tool evaluation, and CI checks that
   guard the rest.

The dependency graph and implementation batches are in
[a_global section 6](a_global.md#6-文档地图与依赖).

## Status and ownership

Every document starts with a status line:

```
> 状态：草案｜基线 `7614ada`｜最后更新 YYYY-MM-DD
```

| Status | Meaning |
| --- | --- |
| 草案 | The design is proposed; implementation has not started. |
| 部分实施 | Some phases have landed; the document states which ones. |
| 已实施 | The design is current behavior; the document points to its files. |

Update the status line and the affected sections in the same pull request that
implements a phase. Once implemented, rewrite the "target design" prose into
the behavior the repository actually has and remove superseded sections; git
keeps the history. Documents that no longer guide future work should be
deleted rather than kept as historical narrative.

Design changes follow the same pull request review as code. The review checks
that the design matches the implementation, that links resolve, and that
validation claims use the vocabulary in
[`docs/STYLE_GUIDE.md`](../STYLE_GUIDE.md).

## Assets

`assets/target_architecture.svg` and `assets/slice_before_after.svg` are the
editable sources for the architecture figures referenced by
[a_summary](a_summary.md). Keep the SVG source in the repository; update the
figure and its references in the same change.
