# Review: YAM / BEHAVIOR 适配改动

- **review 对象**：`feature/yam` 分支工作区相对 `main` (24541d6) 的全部未提交改动 = YAM 双机械臂 + BEHAVIOR 机器人适配（18 个文件修改 + 新增 `robots/yam/`、`robots/behavior/`、`scripts/`、`tests/yam/`、`docs/yam/`、`docs/source-*/usage/behavior.rst`）。该改动集与 `rpent_yam_old`（YAM 工作区，非 git）内容完全一致。
- **框架基线**：main tip `24541d6`（baseline 之上还有 `3f6e247`/`371ac90`/`c4e6254`/`24541d6` 4 个新 commit，涉及 task_card/molmo/e2e-tests/CI，均未被本改动覆盖回退）。
- **检查维度**：正确性、与框架既有契约/API 的一致性、代码风格一致性、doc 准确性。
- **验证方式**：静态 review + 复现（venv 见 `venv/`，日志见 `log/`，problems 见 `problems.md`）。

---

## HIGH

### H1. `robots/behavior/toolkit.py:33` 导入不存在的 `ToolResultEvent`，behavior 运行必崩 ✅ 已复现
```python
from rpent.dashboard.events import (DashboardEventSink, NullDashboardEventSink, ToolResultEvent)
```
`rpent/dashboard/events.py` 只有 `TranscriptEvent`/`UsageEvent`/`RuntimeStatusEvent`/`StepRecordEvent`/`RunStartedEvent` 5 个事件类 + `DashboardEventSink`/`NullDashboardEventSink`，**没有** `ToolResultEvent`（`rpent/planner/api_loop.py:41` 用的 `FunctionToolResultEvent` 是另一个模块的类）。
后果：任何 `import robots.behavior.toolkit`（即 behavior 运行时 `get_toolkit()` 的 `from robots.behavior.toolkit import BehaviorToolkit`）都会抛 `ImportError`。行为机器人无法启动。`toolkit.py:122` 的 `emit(ToolResultEvent(...))` 也依赖同一不存在类型。
修复方向：从 `rpent.planner.api_loop` 引入 `FunctionToolResultEvent`（若 emit 语义匹配），或删除该 emit 分支 / 定义本地事件。

---

## MEDIUM

### M1. `robots/behavior/prompt_bundle.py:67-87` `_cell_items` 期望的 prompt 变量与 `runtime.py parse_config` 提供的 `prompt_vars` 不一致
`_cell_items` 读取：`recipe_tag`/`output_dir`/`job_id`/`attempt_index`/`global_tool_budget`/`tool_budget`。
`runtime.py:279-299` 的 `prompt_vars` 提供了 task/task_language/public_seed/behavior_mode/max_episode_steps/wall_clock_seconds 等，但**未提供** `recipe_tag`（tag）、`attempt_index`（attempt）、`tool_budget`（tool budget）。`output_dir` 由 `rpent/cli/main.py:393` 注入，存在。
后果：system prompt 中 "tag" / "tool budget" / "attempt" 行永远缺失（`_cell_items` 对缺失值静默省略，不报错），agent 缺少当前 cell 标识与预算信息。

### M2. `robots/yam/hardware_ownership.py:49-62` CAN 订阅预检在默认配置下形同虚设
`check_subscriptions` 读 `/proc/net/can/rcvlist_*`，将每行首字段与 `self.channels`（默认来自 `config.example.json` 的 `"can_left"`/`"can_right"`）比对。而 `/proc/net/can` 首字段是内核 SocketCAN 接口名（如 `can0`）。默认配置下永不匹配，预检静默通过。
（若 yam 部署要求用户把 channel 配成真实内核接口名，需在 config 与文档中明确；当前 example 配置与预检逻辑不一致。）

### M3. `robots/behavior/runtime.py:236` `args.activity_instance_id` 校验为死代码
`add_cli_args` 定义了 `--activity-instance-dir`，但从未定义 `--activity-instance-id`。CLI 路径下 `getattr(args, "activity_instance_id", None)` 恒为 `None`，第 236-242 行校验分支不可达（仅 dashboard 显式注入该属性时生效）。

### M4. 文档与代码不一致：BEHAVIOR `motion_unavailable`
- `docs/source-en/rst_source/usage/behavior.rst:293`、`docs/source-zh/rst_source/usage/behavior.rst:279` 写部署返回 `manual_motion_unavailable`；
- 实际 `robots/behavior/rlinf_env.py:1283` 返回 `"stop_reason": "motion_unavailable"`。

### M5. 文档与代码不一致：`robots/yam/guides/GUIDE_RPENT.md:54-57`
GUIDE 称几何 guard "does not cover arm links, self-collision, two-arm collisions"，但 `geometry.py` 的 `_ModelCollisionGuard`（`_validate_model` 要求 "cross-arm collision pairs"、`check()` 对 left/right 前缀 body 对做 mesh 距离检查）已覆盖交叉臂碰撞对。文档过时。

### M6. `robots/behavior/toolkit.py:53-57` `_FRAME_ARTIFACTS` 定义后从未使用（dead code）

### M7. `robots/behavior/tools.py:410-418` `_envelope` 的默认 `primitive_success` 判定过宽
默认 `not (isinstance(public_payload, dict) and public_payload.get("error"))`，即"无 error 键即成功"。后端返回 `{"success": False, "stop_reason": "motion_unavailable"}` 这类无 error 键的失败结果时会被标记为 `primitive_success=True`。

### M8. `robots/behavior/env_client.py:202-213` `reset()` 不清除成功锁存状态
`_official_success_latched`/`_official_success_receipt` 在 `reset()` 后保留；若 `env.reset` 不在成功后的允许方法集合内，成功锁存后再 reset 会抛错，客户端不可复用（当前靠进程隔离规避）。

---

## LOW

### L1. license header 风格不一致（`robots/yam/` 整目录）
main 现有包（`robots/libero` 等）与 `robots/behavior/*` 使用 13 行完整 Apache header；`robots/yam/` 下所有 .py 使用压缩/截断版 header（docstring 前仅 3-9 行注释，如 `evaluation.py`/`hardware_ownership.py`/`prompts/*` 只有 3 行，`toolkit.py`/`tools.py` 等 7 行），与仓库其余部分不一致。

### L2. `robots/yam/env_server.py:125` `config["task_name"]` 直接索引，缺键即 KeyError
`YamEnvFacade.__init__` 提供 `metadata or env_runtime_contract(task_name=env.get_task_language())` 的 task_language 回退，但 `main()` 总是显式传 metadata（用 `config["task_name"]`），无缺键 fallback；且把"任务语言"当 `task_name` 的回退分支在 main() 下不可达。

### L3. `robots/behavior/rlinf_env.py:331-346` `_exact_config_from_official` 对自定义 overlay 缺键抛裸 KeyError
直接访问 `overlay["changes"]["env.flatten_obs_space"]` / `["task.termination_config.max_steps"]`，缺键时抛 KeyError 而非可读校验错误。

### L4. `robots/behavior/rlinf_env.py:42` `ACTION_HORIZON=32` 定义后未使用（dead code，与 `schemas.py` 的 `DEFAULT_ACTION_CHUNK` 重复）

### L5. `robots/behavior/toolkit.py:229-259` `write_recipe` 主路径与 fallback `recipe_records()` 的 JSONL 结构不一致
`state.save` 成功时手写 fallback 分支不可达；两条路径产出结构不同，后续读取方需兼容两套 schema。

### L6. `robots/behavior/harness.py:289` `parser.error("unsupported command")` 不可达（required subparser 在 parse 阶段已退出）

### L7. `robots/behavior/vla_server.py` VLA seed 与 `public_seed` 脱钩（`--seed` 默认 0，runtime 启动 VLA 不传 seed）

### L8. `robots/yam/projection.py:29,58` 相机畸变模型名匹配脆弱
按下划线枚举名（`inverse_brown_conrady`）匹配，RealSense `str(intr.model)` 可能返回带空格的 `"Inverse Brown Conrady"` 而误报 unsupported。

---

## 复核结论（agent 报告经人工核实）
- `robots/yam/geometry.py:421` `mj_saveLastXML(xml_path, kin.model)`：**非问题**。pyproject 固定 `mujoco==3.3.0`，该版本 `mj_saveLastXML(filename, model)` 传参会保存指定模型，左右臂用 prefix 区分 attach，逻辑正确。
- `robots/yam` 与 `robots/behavior` 的 env_server ↔ env_client / rlinf_env RPC 方法一一对应，未发现契约缺口。
- `robots/yam/rlinf_env.py` reset 采用 operator ready receipt 机制（真实机器人安全设计），合理。

## 复现验证结果（venv 见 `venv/`，日志见 `log/`）

环境：micromamba python 3.11.16；`pip install -e . --no-deps` + 手动装基础依赖（国内镜像）。

| 项目 | 结果 |
|---|---|
| `import robots.behavior.toolkit` | **FAIL** → `ImportError: cannot import name 'ToolResultEvent' from 'rpent.dashboard.events'`（即 H1） |
| `import robots.{yam,behavior}.robot_spec` / yam.toolkit / env_client / contracts / evaluation | OK |
| `tests/unit_tests`（排除 `test_codex_contracts`，缺镜像上不可得的 openai_codex） | **256 passed, 3 skipped**（含修改过的 test_main_contracts、test_registry_contracts、test_http_mcp_server） |
| `tests/yam/` | **114 passed**，1 failed（`test_projection.py::test_world_from_depth_rejects_modified_brown_conrady_deprojection`，缺 pyrealsense2），29 skipped（缺 mujoco/pyrealsense2/rlinf） |
| 装 `mujoco==3.3.0` 后 `tests/yam/` | 114 passed；collision guard / path guard 等 mujoco 相关测试通过 |

结论：yam 适配的 CLI 泛化（`supports_exploration` / `default_memory_profile` / `--explore` 路由 / finalization）与 registry 契约在测试层面全部正确；**唯一确定的运行级 bug 是 H1（behavior.toolkit 的 ToolResultEvent 导入错误）**，它不会在 import robot_spec 或 registry 测试时暴露，但 behavior 一进入 `get_toolkit()` 即崩溃。复现过程中遇到的其余问题（镜像缺包、需 PYTHONPATH 等）见 `problems.md`。
