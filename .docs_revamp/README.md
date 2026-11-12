# RPent 文档修复工作区

本目录（`.docs_revamp/`）沉淀盘点结论、修复计划、评审记录与草稿。
文档本体改动落在主目录，即本仓库 `qurakchin/RPent` 的 `docs/revamp` 分支。

- 启动日期：2026-11-12
- 主目录：`/Users/qurakchin/Works/rpent_docs_revamp`，分支 `docs/revamp`
- 分支基线：`upstream/main`，commit `b96cbc1`（feat(session): capture API planner trajectories）
- 目标：让文档与当前实现一致、可照做、中英对称，去掉过时说法与断链

## 范围

| 位置 | 内容 | 规模 |
| --- | --- | --- |
| `docs/source-zh/rst_source/` | 中文用户/开发文档 | 46 个 `.rst` |
| `docs/source-en/rst_source/` | 英文文档，与中文一一对应 | 46 个 `.rst` |
| `docs/STYLE_GUIDE.md` | 写作与页面归属规范 | 353 行 |
| `docs/README.md` | 构建与预览说明 | 86 行 |
| `README.md` / `README.zh-CN.md` | 仓库门面 | 228 / 229 行 |
| `CONTRIBUTING.md` / `CONTRIBUTING_zh.md` | 贡献约定 | 207 / 173 行 |
| `AGENTS.md` / `CLAUDE.md` | agent 工作说明 | 各 65 行 |

现有导航分组：Get Started、Leaderboard、Real-World Demos、Guides、Simulators、
Real-World Robots、Concepts & Development、Resources；`rst_source/` 下的
`get_started/ leaderboard/ real_world_demos/ guides/ simulators/ real_world_robots/
development/ resources/` 与之一一对应。

## 硬约束

1. 以当前实现和调用方为准（`CLAUDE.md` 要求）：文档与代码有分歧时先核实代码，再改文档。
2. 遵守 `docs/STYLE_GUIDE.md`：面向「跑第一个任务的人」、先目的后命令、说明预期结果与失败排查；
   术语中英一致，技术标识符保留原文。
3. 中英页面**相对路径必须一一对应**，章节顺序保持一致；纯中文或纯英文改动要同步另一边。
4. 移动页面必须同时更新内部链接，并在两个 `conf.py` 补旧 URL 映射。
5. 不因「内容不完整」删除已有集成页或占位页；占位页要写清真实状态。
6. 保留现有重要命令、实验数据、图表及其条件；重构时记录内容去向。
7. `.rst` 中行尾 `\` 折行照旧，不顺手重排段落（本仓库既有写作风格）。
8. 未获明确指令不做 `git add/commit/push`、不发 PR 评论。

## 工作流约定

- `audit/`：按页面或按主题的现状盘点（问题、证据、涉及文件行号）
- `plan/`：分批修复计划与验收标准
- `draft/`：需要先写后搬进仓库的草稿（最终以 `rpent_main` 工作树改动为准）
- `review/`：改动后自检/评审记录

## 状态

| 阶段 | 状态 | 备注 |
| --- | --- | --- |
| 工作区建立 | ✅ 2026-11-12 | 记录移入 `.docs_revamp/`；主目录为 `docs/revamp` 分支 |
| 第一轮修复 | ⚠️ 已还原 | 曾在 `rpent_main` 工作树完成 73 个文件改动，用户已还原；记录见 `review/01-改动记录.md` |
| 在新分支重做 | ⬜ | 待做 |
| 构建验收 | ⬜ | `sphinx-build -W --keep-going source-{en,zh}` |
