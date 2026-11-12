# guides 审计（B2）

基线 `main` @ `8503c22`。只读审计。路径均相对仓库根。

## cli.rst（EN/ZH）

- **P1** `--libero-type` 默认值写成「`LIBERO_TYPE` 或 `pro`」（`guides/cli.rst:97` en / `:92` zh）。实现为 `requested or $LIBERO_TYPE or suite_variant(suite)`，单下划线套件推断为 `standard`（`robots/libero/suites.py:44-52`、`robots/libero/robot_spec.py:198-202`）。
- **P2** `--reasoning-effort` 行内嵌「13.2 → 7.9 分钟」数字，无 commit/seed/样本范围（en:43-45、zh:42）。
- **P2** `--am-backend` 只写 LIBERO=`pi05`、RoboTwin=`lingbot`（en:101-102、zh:96），漏 RoboCasa=`rldx`、RoboDojo=`vpp2`、dual_franka/franka/yam=`pi05`（`rpent/robots/components/am_runtime.py:36-44`）。
- **P2** 缺读者/职责句（en:1-4、zh:1-4）。
- **P3** `--memory-profile` 默认值写 `—`（en:63-65、zh:58-60）；实际 `local if explore else hf`，YAM 固定 `local`（`rpent/cli/main.py:444`、`robots/yam/robot_spec.py:131`）。

## configure_planner.rst（EN/ZH）

- **P1** `rpent-check-llm` 失败状态漏 `invalid_model`（en:295-299、zh:221）；HTTP 400 归为该状态（`rpent/planner/check.py:63,78,581`、`rpent/cli/check_llm.py:32`）。
- **P1** `--base-url` 被写成通用覆盖，但 claude_code/codex 拒绝该参数（`rpent/cli/check_llm.py:183-188`、`rpent/cli/main.py:412-417`）。
- **P3** 诊断超时漏 SDK 走 CLI 登录时的 25 s 预算（`rpent/planner/check.py:98,105`）。
- **P2** `--tui` 链接与 quickstart 形成环路；交互权威位置是 `guides/dashboard.rst:9-12`。
- **P3** 缺读者/职责句。

## configure_primitives.rst（EN/ZH）

- **P2** 平台-模型表漏 YAM（en:16-37、zh:16-37），YAM 实际用 Pi0.5（`am_runtime.py:43`、`robots/yam/robot_spec.py:86`）。
- **P2** 缺读者/职责句。
- **P3** 表头「Action model and configuration」只列模型名，无配置。
- **P3** SO-101 说明把 YAM 与占位页并列，读者会误判。

## dashboard.rst（EN/ZH）

- **P1** 只称支持 `api`/`claude_code`/`codex`（en:47-49、zh:34），漏 `flash`（`rpent/dashboard/server.py:140`、`static/dashboard.js:302-306`、`robots/libero/robot_spec.py:88-92`）。
- **P3** 用已弃用 `--interactive`（en:74、zh:54），现为 `--tui`（`rpent/cli/main.py:248-262,380-381`）。
- **P3** 缺读者前提（TTY、浏览器、先完成 quickstart）。

## advanced_deployment.rst（EN/ZH）

- **P2** APXInf 示例用隐藏别名 `--vla-endpoint`（en:78、zh:62），现为 `--am-endpoint`（`am_runtime.py:106-112`）。
- **P2** Dashboard 不支持 `--env-endpoint` 的规则重复展开，应由 `guides/dashboard.rst:74-75` 拥有。
- **P2** 先称 adapter 支持 eval mode，随后说 Dual-Franka/YAM 仍 experimental、未验证（en:84 vs 94-95），「支持」与「实验性」冲突。

## flash.rst（EN/ZH）

- **P2** 安装命令 EN 用官方 PyTorch 源、ZH 用上海交大镜像，命令不一致（en:66-67、zh:44-45）。
- **P2** 「copied unchanged from the merged Flash release… does not constitute a new simulator evaluation」是评审/发布过程叙述（en:32-33、zh:19）。
- **P2** 581/800（72.63%）与缺计划任务的说明重复两遍（en:188-190 与 210-213、zh:135 与 146）。
- **P2** 直接复制发布数字，页面已链接 leaderboard。
- **P3** 「Historical Comparison」整节是历史对比（en:203、zh:141）。

## flywheel.rst（EN/ZH）

- **P3** 原始轨迹路径写成 `task_<id>/seed_<seed>/`（en:34、zh:30），实际为零填充 `task_%02d/seed_%03d/episode_*`（`robots/libero/flywheel.py:59-63,80,103`）。
- **P3** `--output-root` 未写默认值；省略时为 `<data-root>/datasets/lerobot/<suite>/task_XX`（`flywheel.py:106-110`）。

## memory.rst（EN/ZH）

- **P2** 「Release Provenance and Compatibility」整节是历史/流程叙述（en:128-176、zh 约 100-125）。
- **P2** 「Other Environments」漏 YAM（en:225-232、zh:172-177），YAM 支持探索与本地记忆（`robots/yam/robot_spec.py:86,108-110,131`）。
- **P2** 重复 Flash 页拥有的 plan 文件细节（en:139-141、zh:105）。
- **P3** 历史复现命令用旧 client 与 `--memory-dir /path/to/legacy-download/libero`。

## 总体

命令、默认值、路径大多与实现一致；主要问题是「按发布/评审过程写的历史叙述与复制数字」和「平台/规划器覆盖落后于实现（Flash、YAM、invalid_model、废弃别名）」，且多数页面缺读者/职责句与证据限定。
