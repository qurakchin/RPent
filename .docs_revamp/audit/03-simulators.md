# 批次 B3：simulators 组审计

范围：`docs/source-{en,zh}/rst_source/simulators/{index,libero,robocasa,robotwin,robodojo}.rst`（5 对页面）。
基线：rpent_main @ `8503c22`，工作区已有本轮文档改动。

## 已确认并修复

| 页面 | 级别 | 问题 | 依据 | 状态 |
| --- | --- | --- | --- | --- |
| libero（中英） | P1 | RLinf 运行时 extra 写成 `rpent-rlinf` | `pyproject.toml`：extra 名为 `rlinf`，依赖 `rlinf @ git+…@release/v0.4` | 已修 |
| index（中英） | P1 | RoboDojo 描述写「RLinf Pi0.5 策略」 | `robots/robodojo/toolkit.py:43` 只注册 `vpp2_act`/`awomo05_act`；`robot_spec.py` 只分派 `vpp2`/`awomo05` | 已修 |
| robotwin（中英） | P1 | 默认输出目录漏 task-config | `robots/robotwin/robot_spec.py:327` `recipe_tag = f"robotwin_{task_name}_{task_config}_s{seed}"` | 已修 |
| robodojo（中英） | P1 | 缺「任务记忆」说明 | `robot_spec.py:213-215` 只读 `MemoryManager`；`:323-328` `--memory-dir` 默认 `memory/robodojo`；`--explore` 不支持 | 已修（新增小节） |
| robodojo（中英） | P2 | `--random` 时的默认输出目录未写 | `robot_spec.py:320-332`：随机模式 `recipe_tag = f"{task}_random"` | 已修 |
| robocasa（中英） | P2 | 冲突包名 `rlinf-robocasa365` 在本仓/RLinf 检出中均不存在 | `pyproject.toml:145` 实际发行名 `rpent-robocasa365`；导入包为 `robocasa` | 已修（改为描述发行名 + 导入包冲突） |

## 已核对、无需修改

- **libero**：`--libero-type` 推断（`robots/libero/suites.py:44-52`）、三套安装命令与 extra（`libero`/`libero-pro`/`libero-plus`）、checkpoint 与环境变量名、工具清单、进程分工路径 `robots/libero/env_server.py`、`rpent/robots/components/pi05_vla_server.py`、`rpent/robots/components/sam3_server.py`。
- **robocasa**：Target50 资源命令与 `ROBOCASA_ASSETS_PATH`、RLDX 权重与 `--am-endpoint` 口径、`uv pip check` 与 `--no-macros`。
- **robotwin**：`--task-config` 默认 `demo_randomized`、已验证 seed 表链接、`TASK_ENV.eval_success` 成功口径、LingBot-VLA 与 Fast-WAM 分支。
- **robodojo**：VPP2/Awomo05 资源布局、`RPENT_RLINF_ROOT`、`result.json`/`states.json`/`score` 字段、工具签名，均与 `robots/robodojo/{robot_spec,toolkit,primitives}.py` 一致。

## 未解决 / 留给后续

- `robodojo` 的 `--memory-profile hf` 依赖 `RLinf/RPent-memory` 下存在 `robodojo/` 子集；当前无法离线确认该子集是否发布。文档已写成「尝试同步，缺失则用本地目录」，避免承诺。
- 各页「验证状态」段已由主会话在批次开始前统一补齐，本轮未重复改动。
