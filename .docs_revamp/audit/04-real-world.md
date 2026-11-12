# 批次 B4：真机文档审计

范围：`real_world_robots/{index,franka,dual_franka,yam,so101}.rst`、`real_world_demos/{franka,yam}.rst`（中英）。
快照：2026-11-12 11:35，工作区已含本轮「验证状态」段与 SO-101 真实状态改动。审计只读，无 P0。

## P1

| 页面 | 问题 | 依据 |
| --- | --- | --- |
| `real_world_robots/dual_franka.rst`（中英） | 缺安全与停止段：主运行路径没有停止步骤，仅 VLA 诊断台与探索命令提到 Ctrl+C/STOP 且声明不是硬件急停；未写硬件急停/断电与操作员值守 | `docs/STYLE_GUIDE.md:208-221`：部署页须覆盖 stopping 与物理安全约束 |

## P2

| 页面 | 问题 | 依据 |
| --- | --- | --- |
| `real_world_robots/franka.rst`（中英） | 安装节自相矛盾：先要求装 libfranka 0.19.0，后又说 wheel 已内置 0.19.0 | `pyproject.toml:137-139` |
| `real_world_robots/franka.rst`（中英） | 未声明 franky wheel 平台/Python 约束（linux x86_64、3.10–3.12），macOS/3.13 会静默缺 franky | `pyproject.toml:11,137-139` |
| `real_world_robots/dual_franka.rst`（中英） | 工具清单漏 6 个已注册工具：`back_project`、`segment`、`describe_dual_franka_setup`、`recover_joint_posture`、`request_scene_reset`、`request_operator_verdict` | `robots/dual_franka/toolkit.py:545-580`；`robots/dual_franka/tasks.py:118,125,139` |
| `real_world_robots/dual_franka.rst`（中英） | 验证状态段证据不可追溯：称发布说明中「两项任务各完成一次」，发布页只有演示描述，无任务数/单次记录；ZH 还把两项具体化，与 EN 不等价 | `resources/release_v0.1.rst:23-27` |
| `real_world_robots/yam.rst`（中英） | 无安全段/无急停说明 | `docs/STYLE_GUIDE.md:208-221` |
| `real_world_robots/yam.rst`（中英） | 验证状态引用发布说明的「单次成功」，发布页只有演示描述（且含抓取检查、移开遮挡物） | `resources/release_v0.1.rst:23-27` |
| `real_world_robots/index.rst`（中英） | SO-101 行仍写「内容即将推出」，与 `so101.rst` 的「尚未集成」矛盾 | `real_world_robots/so101.rst:4` |

## P3

- `franka.rst`：工具清单漏 `back_project`、`view_perception_setup`（`robots/franka/perception.py:100,123`，`toolkit.py:78-81`）。
- `franka.rst`：Flash 限制写成「每次记录/单步」位移上限，实际校验回放定位后的动作增量（`robots/franka/flash/replay.py:165-167,181-183`）。
- `franka.rst`（ZH）：`realtime_config` 语义与 EN 相反（EN：在 PREEMPT_RT 内核上改 `enforce`；ZH 写成「需要强制在 PREEMPT_RT 上运行才改」）。
- `franka.rst`（EN）：验证状态引用 “Safety Requirements”，章节名为 “Safety”。
- `dual_franka.rst`：`--camera d455` 示例与 example.yaml 同时启用 `base`/`d455` 两个 projection view 的关系未说明（`robots/dual_franka/config/example.yaml:102-111`）。
- `dual_franka.rst`：d455 候选文件名含糊，求解器固定输出 `base_camera_extrinsic_candidate.json`（`calibration_tools/solve_base_handeye.py:269`）。
- `yam.rst`：无意义标签 `_id1`–`_id5`、`_dashboard` 跨页复用；手动测试漏 `status`/`stop`（`robots/yam/manual.py:106-110`）。
- `real_world_demos/franka.rst`：标题 Dual-Arm Franka，路径名 `franka` 与单臂页语义冲突。
- `docs/source-*/index.rst:51`：YAM 链接指向演示页而非部署页。

## 已核对通过

`--robot` 名与 `robots/` 目录一致；三份 `config/example.yaml` 路径与关键字段一致；双臂标定端口、样本数、ArUco 参数与 `calibration_tools/` 一致；YAM 的 env_server/operator_control/manual/VLA 参数、任务 0–2、`result.json`/`states.json`/`episode_*.mp4` 一致；演示页 `:doc:` 链接正确。

## 处理结果

- P1（dual_franka 安全与停止）、P2（franka 安装矛盾/平台约束、工具清单、验证状态口径、SO-101 索引行）与 P3 全部已修。
- `yam.rst` 的「停止与退出」补操作员值守、软件停止（`env.request_stop` / `operator_control --event abort` / manual `stop`）与硬件急停边界。
- `franka.rst` 工具清单再补 `back_project_correspondence`（`robots/franka/perception.py:268-269`，由 `iter_tools` 自动注册）。
- 外部 pin（i2rt commit、HF checkpoint revision、RLinf 链接）仍未联网核验。

## 未核验

YAM 外部 pin（i2rt commit、HF checkpoint revision）与 RLinf 文档链接未联网确认。
