# RPent Documentation Style Guide

Use this guide for English and Chinese documentation, examples, comments, and
user-facing messages. Verify behavior against the code being documented. Build
instructions are in [README.md](README.md).

This guide adapts the writing and presentation principles in
[RLinf's documentation guide](https://github.com/RLinf/RLinf/blob/main/docs/STYLE_GUIDE.md)
to RPent's task execution, memory, and robot workflows. RPent's navigation and
page boundaries are defined below.

## Write for someone running their first task

Open with what the reader will accomplish. State the prerequisites before the
first command. Explain each command's purpose, then show the expected result
and where to look if it fails. Keep one complete, copyable path through a
tutorial; place alternatives after that path or link to their own guide.

Use short, direct sentences and familiar technical terms. Explain a concept
before introducing its internal identifier. Keep implementation details in
developer pages unless they affect a user's choice or operation.

Keep explanations connected. Introduce each section with its purpose before
showing a command, table, or interface. Explain the expected output and how it
informs the next step. Concepts pages should explain how components cooperate,
not just enumerate classes and methods. Concision must preserve prerequisites,
conditions, exceptions, ownership, and the reasons a reader needs to act.

Describe current behavior and necessary constraints. Do not narrate a review
exchange or the process of replacing one implementation with another.

| Avoid | Prefer |
| --- | --- |
| The corrected installer no longer treats a nonempty directory as complete. | `--skip-existing` checks the downloaded file inventory. |
| This isn't just a few more motions; it unlocks endless evolution. | The planner checks observations after each tool call and selects the next action. |
| 修正后的安装器不再覆盖旧资源。 | 内容不同的已有资源会保留；使用 `--overwrite` 可替换安装范围内的资源。 |

Keep negative statements when they explain a real limit, failure condition,
safety requirement, or compatibility boundary. Put migration history and
version-specific changes in release or migration notes.

## Navigation and page ownership

Keep the same sections and ordering in both languages:

The navigation has one primary axis: the reader's task. Stage, evidence type,
page type, and audience are secondary; never promote one of them to a
top-level group. Each group answers one question:

1. **Get Started / 开始使用**: What is RPent, and how do I complete one task?
   Introduction and Quick Start.
2. **Simulators / 仿真环境**: Which simulated platform do I run, and how do I
   reproduce its results? LIBERO, RoboCasa365, RoboTwin, and RoboDojo. Each page
   owns its installation, first run, reproduction protocol, and troubleshooting.
3. **Real-World Robots / 真实机器人**: How do I deploy and operate a physical
   robot safely? Single-Arm Franka, Dual-Arm Franka, YAM, and SO-101. Preserve
   coming-soon pages and describe their actual status.
4. **Real-World Demos / 真实世界演示**: What does a task look like on the
   hardware? Each demo links to the corresponding installation and operation
   page.
5. **Leaderboard / 排行榜**: How do the reported methods compare, and what do
   the numbers count? Performance, time and token costs, and the evaluation
   protocol.
6. **Guides / 使用指南**: How do I configure a feature? Memory and exploration;
   action primitives and tools; planner configuration; command-line reference;
   interactive usage; Flash Mode; data flywheel; remote services; troubleshooting.
7. **Concepts & Development / 原理与开发**: How does RPent work inside, and how
   do I extend it? Architecture, interfaces, memory design, and extension guides.
8. **Resources / 项目资源**: What does the paper report, how do I contribute, and
   what changed in v0.1? Harness VLA, contributing, and release notes.

If two groups can be described by the same question, merge them. If a group
cannot be described in one question, the axis is wrong.

Match source directories to the sidebar groups in both language trees:

| Sidebar group | Directory under `rst_source/` |
| --- | --- |
| Get Started | `get_started/` |
| Leaderboard | `leaderboard/` |
| Guides | `guides/` |
| Simulators | `simulators/` |
| Real-World Robots | `real_world_robots/` |
| Real-World Demos | `real_world_demos/` |
| Concepts & Development | `development/` |
| Resources | `resources/` |

Use non-clickable group captions with consistent spacing in the sidebar.
When moving a page, update internal links and add an old-to-new URL mapping
in both `conf.py` files. Keep the same relative page paths in both languages.

The home page is a short introduction with task-oriented links. Installation
and the first LIBERO-PRO task form one Quick Start. Keep reproduction inside
each environment page; logs, success criteria, and common failures belong
next to the procedure they explain. Keep the leaderboard's published data, its
protocol page, and the two results pages intact when reorganizing prose.

Preserve important commands, reported data, figures, and their experimental
conditions when moving content. Record their destination during a restructure;
brevity alone is not a reason to delete them. Verify intentional corrections
against the source and document the reason in the change description.

Use short sidebar labels and descriptive page headings. Keep existing page
URLs where practical. If content moves, preserve useful anchors and provide a
clear route from the old page. Do not delete an integration or placeholder
solely because it is incomplete.

## Terms and single sources

Write **LIBERO-PRO** in prose, headings, and table labels. Keep lowercase
`libero-pro` only in code identifiers: the `.[libero-pro]` extra, suite names,
and `--libero-type pro`. Do not use “LIBERO Pro” or “LIBERO-Pro” in prose;
preserve an upstream repository or dataset name that is genuinely spelled that
way.

Keep each published benchmark number in one place: `results.json` and the
leaderboard pages that render it. Other pages state the configuration and link
to **Performance** or **Evaluation Protocol** instead of repeating rates,
counts, or aggregates. When a page must explain an aggregate, describe the
rule (mean of suite rates, pooled episodes) rather than restating the headline
value. The same rule applies to model, branch, and reasoning settings: keep the
complete reproduction configuration on the simulator page and let the
leaderboard own the resulting numbers.

Declare new command-line entry points in the **Command Entry Points** table on
the architecture page, including the distribution that defines them. Keep
dependency-package scripts (asset downloaders and simulator helpers) distinct
from the four `pyproject.toml` commands.

## Page structure

### One opening, one route

Every page except pure directory and generated results pages opens in this
order:

1. H1 title.
2. An optional overview figure.
3. A ``page-head`` directive with four required options:
   ``:for:`` (who the page is for), ``:outcome:`` (what the reader can do
   afterwards), ``:read-when:`` (the situations that call for this page), and
   ``:skip-when:`` (the situations that do not, with a link to the page that
   does). Write applicability and non-applicability, not a table of contents.
4. One or two sentences of context. Do not repeat the page-head fields.
5. A **Page map** paragraph (`**Page map:**` in English, `**本文结构：**` in
   Chinese) that lists the page's top-level sections in the order they appear,
   joined by `→`. The page writes this route; it is not the sidebar's "On this
   page" list. List the H2 sections, and add an H3 only when it is a main route
   choice such as WAM Evaluation. Name the first-run path first, then reference
   sections, then diagnostics. When the page has a clear strategy, say so in
   the map, for example "shortest runnable path → options → common problems".

The page-head gives a reader the three facts needed to decide whether to stay:
who it is for, what it produces, and when to leave. The page map then makes the
reading order predictable. Update both when the section structure changes.
Omit the page map only on pages with one or two sections, such as a demo page,
a coming-soon page, or a generated results page. The structure checker
(``_checks/check_structure.py``) requires a page-head on every page with two or
more H2 sections and a page map on every page with three or more.

Within a section, put the decision-relevant content first: the command or
answer, then its explanation, then optional details. Move optional material to
the end of the section or a `dropdown` directive. Never open a section with a
history note or a list of unsupported cases.

### Home and directory pages

Use a centered logo and heading on the home page, followed by a short
introduction and task-oriented cards. Keep ordinary page text left-aligned.
Directory pages introduce the reader's choice and route to child pages with
cards or a table containing a short description for each entry. Do not use
bare link lists as the visible directory. Use hidden toctrees where a page
owns navigation; compatibility entry pages can link to pages already owned
by the main navigation without adding another toctree.

Use the shared sidebar, font stack, and spacing. Keep equivalent navigation
labels consistent in both languages. Check short pages as well as long ones:
removing a local table of contents must not leave an empty column before the
article. Site features such as an AI assistant or live repository star count
are separate from documentation content requirements.

### Quick Start

Use this sequence: requirements, installation, assets and checkpoints, planner
connection check, one task, expected artifacts and success criterion, common
failures. Keep runtime option tables in Command-Line Reference. Put installation
commands and optional dependency groups in the environment or feature guide
that uses them; do not maintain a separate installation-extras summary table.

### Simulator guides

When an official overview figure helps explain the environment, place it below
the page title, followed by a short explanation of the task the reader can run
with RPent. Follow the RLinf LIBERO and RoboTwin pages: center the figure, use
`:width: 90%`, preserve its aspect ratio, and credit its source in the caption.
Use an image of the documented environment version. Figures are optional;
do not add a decorative image just to fill this position. Describe upstream
results within a figure as upstream results, not RPent experiment evidence.
Give the image descriptive alt text and keep section anchors outside the
figure directive. Check the rendered image, caption, and following heading in
both languages.

Start with **Overview / 概览**. Use four `sphinx-design` cards with the same
titles and order across simulator pages: **Action Models / 动作模型**,
**Planners / 规划器**, **Tasks / 任务**, **Hardware / 硬件**. Use
`.. grid:: 2 4 4 4` with `:gutter: 2` and brief, left-aligned descriptions.
List supported configurations, and link special modes to their prerequisites.
RPent coordinates task execution, so these cards describe planners rather
than RL training algorithms.

After Overview, put the first-run path first: installation and resources,
model and planner configuration, **Run a Task / 运行一个任务**, and
**View Results / 查看结果**. Place reference sections — **Tasks / 任务** and
**Observation and Action / 观测与动作** — after that path, so task and option
tables do not push installation and the first command below the fold. Use
tables for both. The task table identifies suites or task categories and their
scope; keep detailed task/seed matrices with reproduction. The interface table
uses the same rows: **Observation / 观测**, **Action / 动作**,
**Reward / success / 奖励与成功判定**, and **Task prompt / 任务指令**. Distinguish
what the planner sees from model inputs or native control commands where it
matters. State the native success signal without inventing a training reward
or treating the planner's `finish` response as the evaluation outcome.

After Overview, cover:

1. System and Python requirements, installation, and resource downloads.
2. Model and planner configuration, with one concrete runnable task.
3. Result files and the environment's native success criterion.
4. Task selection and other environment-specific options, then the Tasks and
   Observation and Action reference tables.
5. Memory and exploration.
6. Reproduction: code version, resource revisions, task/seed matrix, model
   settings, limits, retry policy, and aggregation method where available.
7. Common failures and relevant diagnostics.

Use the same headings and levels for sections with the same purpose.
Required sections apply to each supported simulator; include conditional
sections when the stated feature is supported or results are published.
Keep this order for every simulator page:

| # | English | Chinese | Level | Requirement |
| --- | --- | --- | --- | --- |
| 1 | Overview | 概览 | H2 | Required |
| 2 | Installation | 安装 | H2 | Required |
| 3 | VLA Configuration | VLA 配置 | H2 | Conditional: a VLA checkpoint must be prepared |
| 4 | SAM3 Configuration | SAM3 配置 | H2 | Conditional: segmentation is used |
| 5 | Run a Task | 运行一个任务 | H2 | Required |
| 6 | View Results | 查看结果 | H2 | Required |
| 7 | Task Selection | 任务选择 | H3 under Run a Task | Conditional: the environment has more than one task-selection flag |
| 8 | WAM Evaluation | WAM 评测 | H2 reference section after the first-run path | Conditional: a WAM backend is supported |
| 9 | Tasks | 任务 | H3 under Run a Task | Required |
| 10 | Observation and Action | 观测与动作 | H2 reference section after the first-run path | Required |
| 11 | Validation Status | 验证状态 | H2 reference section after the first-run path | Required |
| 12 | Task Memory | 任务记忆 | H2 | Conditional: memory is supported |
| 13 | Exploration Mode | 探索模式 | H2 | Conditional: exploration is supported |
| 14 | Common Options | 常用参数 | H2 | Conditional: the environment adds run options |
| 15 | Experiment Reproduction | 实验复现 | H2 | Conditional: benchmark results are published |
| 16 | Tools the Planner Can Call | 规划器可调用的工具 | H2 | Conditional: the tool surface needs explanation |
| 17 | Page-specific sections | 页面专属章节 | H2 | Conditional: Dashboard, deployment, diagnostics, implementation notes |

Installation owns both the environment setup and its asset downloads. When
asset downloads form their own procedure, put them in a
**Download Assets / 下载资源** H3 and keep the install prose above it; when a
single table row covers them, keep them inline. VLA Configuration owns
checkpoint download and model-specific settings; do not create separate
**Download the Model** sections.

Keep a platform page at or below 13 H2 sections. Short setup detail becomes an
H3 under the step it supports instead of a new top-level chapter: task
selection, planner-specific setup such as Codex login, manual skill checks, and
data collection or training under VLA Configuration. Reference material that
belongs with a step follows the same rule — put **Tools and State Artifacts**,
**HF corpus selection**, and a tasks table under View Results, Task Memory, and
Run a Task respectively. A section that answers a genuinely different question,
such as Task Memory, Exploration Mode, or Experiment Reproduction, stays an H2.
When a page still exceeds the limit, split it rather than nesting unrelated
material. The structure checker enforces the limit.

Use **Task Memory / 任务记忆** and **Exploration Mode / 探索模式** as separate
H2 sections, even when one of them is short. Use **Experiment Reproduction /
实验复现** as the shared heading without qualifiers; state the benchmark name
(Target50, for example) in the first sentence of that section. Keep
environment-specific diagnostics after the reproduction section. Preserve
existing named anchors when renaming headings.

Use links to shared guides instead of repeating generic planner, memory, or
Dashboard instructions. Preserve environment-specific requirements. Never
present a single successful task as validation of a complete benchmark.

Name an overview section **Overview / 概览** on every page that has one. Name
in-page failure guidance **Common Problems / 常见问题**; only the shared guide
uses the page title **Troubleshooting / 问题排查**.

State software and accelerator requirements from the supported setup. Report
verified GPU models and memory usage only when there is evidence; distinguish
measurements from estimates or minimum requirements. Add a separate hardware
backend subsection only when its installation, device options, rendering, run
command, and limitations are documented and supported. Do not copy another
project's accelerator claims.

### Role sequences by family

Define the role order once per family. A family page uses the same roles in the
same order; only optional roles disappear. An entry page may add one
**global route** section before the sequence, and must not change the order of
the remaining roles.

| Family | Role sequence |
| --- | --- |
| Simulator | Overview → Installation → model configuration → Run a Task → View Results → task/reference sections → memory and exploration → Experiment Reproduction → Common Problems |
| Real-world robot | Safety and Stopping → Installation → Calibration → Robot Configuration → model configuration → Start Services → Run a Task (task selection, planner setup, and manual skill checks as H3) → View Results (tool reference as H3) → Verification Status → Exploration Mode and replay |
| User guide | What this guide covers → prerequisites → the procedure → how to check the result → options and reference → Common Problems → next step |
| Developer guide | Contract or purpose → numbered steps 1..n → conventions and reference → tests → next step |

The platform and robot tables above are the authoritative role names for those
two families. The guide and developer families use these role names:

- **Procedure:** *Use Published Memory*, *Record a Trajectory*, *Run a Plan*,
  *Start Services*; do not rename one guide's procedure to "Usage" or "Workflow".
- **Result check:** *View Results*, *Verify Your Configuration*, *Validate the
  Planner*; name the object being checked.
- **Reference:** *Common Options*, *Command-Line Reference*, *Reference*; put
  parameter tables here, not between procedure steps.
- **Failure guidance:** *Common Problems* in a page; *Troubleshooting* only as
  the shared guide's title.

### One name per role

Within a family, one role has one name. A second name for the same role is a
defect: rename the page, do not add a synonym to the style guide. Across
families, names may differ when the role differs; for example, a simulator's
**Tasks** reference is not the same role as a robot's **Task Selection**
procedure. Page-local sub-steps (H3) do not count as new role names.

When a fact changes, update its owner page first, then the pages that link to
it. The canonical-location table in `README.md` is the list of owners for
commands, defaults, credentials, memory, results, and architecture; add a row
there before repeating a fact on a second page.

### Real-world robots and demos

Use a clear introductory robot photo with alt text, a short caption, and
`:figclass: rpent-robot-figure` for shared sizing. Preserve the image's
proportions and check desktop and narrow-screen layouts. Keep the source URL
in the RST; add a visible credit when the asset's terms require it.

Deployment pages put safety first and then follow this order, omitting a
section only when the robot does not need it:

| # | English | Chinese | Level | Purpose |
| --- | --- | --- | --- | --- |
| 1 | Safety and Stopping | 安全与停止 | H2 | Operator responsibilities, emergency stop, and shutdown |
| 2 | Installation | 安装 | H2 | Package, driver, and controller setup |
| 3 | Calibration | 标定 | H2 | Hand-eye or arm calibration |
| 4 | Robot Configuration | 机器人配置 | H2 | Robot file, workspace, and safety limits |
| 5 | VLA Configuration | VLA 配置 | H2 | Checkpoint and endpoint; data collection and training as H3 |
| 6 | Start Services | 启动服务 | H2 | Ray or two-machine startup |
| 7 | Run a Task | 运行一个任务 | H2 | One runnable task; task selection, Codex setup, and manual skill checks as H3 |
| 8 | View Results | 查看结果 | H2 | Artifacts and success criterion; tools and state artifacts as H3 |
| 9 | Verification Status | 验证状态 | H2 | What has actually been validated |
| 10 | Exploration Mode | 探索模式 | H2 | Operator-assisted retries, when supported |
| 11 | Flash Replay | Flash 回放 | H2 | Plan replay, when supported |

Put **Safety and Stopping** before **Installation** and keep the hardware
emergency stop distinct from software shutdown. Use **Start Services** rather
than naming Ray or the machine count in the heading; state the topology in the
section's first sentence. Do not keep a second **Safety** section later on the
page. Keep operator responsibilities and physical safety constraints explicit.

Demo pages describe the task, embed the video, and link to the corresponding
installation and usage guide. Clearly mark pending instructions and coming-soon
integrations so readers know which workflows they can reproduce.

### Guides and developer pages

User guides explain a task with prerequisites and examples. Developer pages
explain ownership, interfaces, call flow, and extension points. Verify
signatures, argument types, defaults, lifecycle, and actual callers. Keep
illustrative code clearly distinct from executable examples.

Use Command-Line Reference as the shared reference for parameter defaults,
environment variables, and output files. Link to it from
tutorials. Specify which environment or mode owns a default. Keep internal
storage formats separate from supported inspection tools and public APIs.

Cover terminal interaction and Dashboard operation together in Interactive
Usage. Explain how to start, submit instructions, and end a session, including
planner-specific differences and environment restrictions.

## English and Chinese

Keep matching page paths, navigation, commands, prerequisites, limits, and
results. Translate meaning into natural Chinese; do not copy English sentence
structure. Preserve code identifiers, model names, flags, and filenames.

| English | Chinese usage |
| --- | --- |
| planner | 规划器; keep `--planner` unchanged |
| memory | 记忆; use “任务经验” when describing its contents |
| exploration | 探索模式 |
| recipe | 动作序列 or 任务策略, depending on the file's contents; keep `_recipe.jsonl` unchanged |
| checkpoint | 模型权重 or checkpoint, depending on context |
| rollout / episode | 一次任务运行 / 一次尝试, when that is the intended meaning |
| success criterion | 成功判定 |
| Real-World Robots | 真实机器人; in prose use 真机 for one physical robot |
| Simulators | 仿真环境 |
| evaluation | 评测; do not use 评估 for the same concept |
| vision-language-action (VLA) | 视觉—语言—动作（VLA） at first use on a page, then VLA |
| remote procedure call (RPC) | 远程过程调用（RPC） at first use on a page, then RPC |
| WAM | a second action-model family alongside VLA; describe its role at first use, and do not invent an expansion |

Write current behavior, not a summary of why the change matters. Remove
sentences that raise the tone without adding a fact ("this closes the loop",
"it is not just X but Y", "ultimately"). A technical page does not need a
closing paragraph that restates its importance. Split a Chinese sentence longer
than about 40 characters into an action, its object, and its condition; put a
long condition first or in its own sentence.

Use Chinese punctuation in Chinese prose and spaces between Chinese text and
Latin identifiers. Chinese prose paragraphs and list items may stay on one
source line or wrap with a trailing backslash (`\`) to escape the newline.
Keep list and directive indentation. Escaped line breaks remove whitespace,
so use them between Chinese characters, not where a word separator is needed.
For example, this renders as one sentence without a space at the line break:

```rst
评测模式读取已有记忆，\
按环境规定判断任务结果。
```

Preserve line structure in tables, code blocks, and raw HTML; this prose rule
does not apply inside literal blocks. English prose may wrap at normal source
line lengths.

RST inline markup needs boundaries around Chinese text. Write
`使用 ``base_camera`` 相机` rather than gluing backticks to adjacent Chinese
words or punctuation. For emphasis, prefer plain Chinese or quotation marks
when `**...**` would touch Chinese characters. Check the generated HTML for
literal asterisks, backticks, and code spans that accidentally include prose.
Use Chinese punctuation in prose while preserving exact command syntax.

Use “RPent 简介” as the introduction title. Use “RoboCasa365” for the documented
simulator version, while keeping the CLI identifier `robocasa` unchanged.

## Figures and visual language

Define the visual language before drawing a figure, and use the same one on
every page:

- **Color.** Four semantic colors, all at the same lightness: green for user
  entry, the site's primary purple for the agent, the secondary magenta for
  services, and neutral gray for environments. Take the purple and magenta from
  `_static/css/custom.css`; do not introduce a second palette.
- **Shape.** One node shape (rounded rectangle) and one title/detail type
  scale. Do not mix default Graphviz shapes or fonts.
- **Arrows.** Solid is a call, dashed is an input or an error return, and a
  double arrow is a shared connection. State this in the legend and in the
  caption.
- **Size.** One figure answers one question and stays at or below 12 nodes. If
  it needs more, split it into an overview and a detail figure. Labels are at
  most two lines.
- **Caption.** Write how to read the figure, not what it is called: start with
  "Read from top to bottom" (从上往下读), then name the start, the path, and the
  end. A reader who covers the details should still be able to state the main
  flow in five seconds.
- **Source.** Generate SVGs with `make diagrams` from `_diagrams/make_diagrams.py`;
  do not hand-edit an SVG. The figure must remain readable at page width, and
  its text must not shrink below body size when the page is scaled.

Screenshots follow the same rule: show the current version, add a caption that
names the version and what to look at, and keep the UI text readable at page
width. Do not add a screenshot that cannot be reproduced from the documented
steps.

## Formatting and media

- Give each page one visible H1. Use `=` for the page title, `-` for sections,
  and `~` for subsections. Use title case for English headings.
- Keep prose and cards left-aligned. Use the shared CSS for font stacks,
  spacing, content width, and media. Do not style individual paragraphs or
  add duplicate raw-HTML titles.
- Use `:doc:` and `:ref:` for internal links. Keep hidden toctrees on the home
  page for sidebar organization.
- Use tables for comparisons, numbered lists for procedures, and code blocks
  for commands. Introduce examples and explain what their output means.
- Use `.. note::` for a relevant constraint and `.. warning::` for an actual
  operational risk, such as incompatible packages, device selection, or robot
  startup order. Put the warning beside the affected step and explain the
  condition and the required action. Keep optional details out of the main
  installation path.
- Put reusable RST fragments in underscore-prefixed files excluded from page
  discovery. Share repeated instructions when they have the same contract;
  do not merge instructions with different environment prerequisites.
- Use direct media URLs, meaningful alt text, captions, and video controls.
  Check media links and both light and dark themes. Keep media responsive and
  avoid replacing ordinary text with screenshots.

Verify image, poster, and video URLs return HTTP 200 before handoff. Inspect
new figures and confirm video playback in the rendered page. Preserve useful
alt text, visible captions, and source credits. Report blocked checks instead
of treating an unchanged URL or a successful Sphinx build as availability
evidence. Check transparency and contrast in dark mode; avoid a forced white
background on transparent logos.

## Preserve information during restructuring

Compare against an explicit Git revision and the pre-edit working tree. Track
where important commands, dependency options, parameter defaults, outputs,
tables, figures, videos, and constraints move. Explain deliberate removals in
the change description and verify replacements against the current code.

Compare tables by their labels and values, not only their count. Preserve
task/seed coverage, denominators, failure and timeout handling, aggregation,
model settings, resource revisions, and timing boundaries with every reported
result. Moving a table must not detach its qualifications. A simplified quick
start should link to complete reference information elsewhere.

Retain useful page URLs and section anchors when renaming or moving content.
Check their destinations in generated HTML, including cross-language links.
Preserve coming-soon integrations and clearly state their documented status.

## Verify before handing off

Read every changed paragraph in both languages. Check commands, paths,
defaults, support claims, and result definitions against their code consumers.
Check that required content and existing placeholders remain reachable, that
reproduction data is unchanged, and that demo links reach the right robot.

Build both languages with warnings treated as errors:

```bash
sphinx-build -W --keep-going docs/source-en docs/build/html-en
sphinx-build -W --keep-going docs/source-zh docs/build/html-zh
```

Inspect rendered pages on desktop and narrow screens, including dark mode,
sidebar order, headings, tables, code, media, and the language switcher.
Check command blocks for shell syntax and bilingual consistency. Review all
changed prose manually: matching commands do not establish semantic parity.
Inspect index presentation, section introductions, and Chinese inline markup
in addition to build warnings. Compare preserved content with the recorded
baseline after the final edit, including leaderboard files and media URLs.
Report static checks, builds, and actual service or robot runs separately.
A clean documentation build does not establish that a command completed a
real task.
