# a_summary 改造后的目标形态
> 状态：草案｜基线 `01e9cb3`｜最后更新 2026-11-13

> 汇总目标架构、模块对照、目录设计、代码量与文件量，以及改造本身的成本和取舍。
>
> 前置阅读：[a_global](a_global.md) 第 1–3 节。基线 `01e9cb3`，口径见 a_global 5.1；名字与路径以 a_global 2.1 为准。

## 1. 一句话

改造后，RPent 从「每个机器人一条垂直栈」变成「按能力水平分层」：

- **核心全仓一份**：环境契约与 client/facade、工具族与 Toolkit、结果契约、prompt 片段、运行产物、安装器、验证护栏；
- **共享能力独立成组件**：模型服务在 `capabilities/`，需要独立评估的工具在 `toolkits/`；
- **切片只保留接入部分**：`spec.py`、`config.py`、`adapter.py`、`prompts/domain.py`，按需的 skill binding 和原生特有工具；
- **差异化功能保持不变**：Flash、分层记忆、真机运营与安全。

## 2. 目标架构

![RPent 目标架构](assets/target_architecture.svg)

> 图源：[`assets/target_architecture.svg`](assets/target_architecture.svg)。左侧是核心（全仓一份），右侧虚线框是切片实现；每一层标注了负责的主题文档。

| 层 | 核心（全仓一份） | 共享组件 | 切片 | 文档 |
|---|---|---|---|---|
| Planner 运行时 | claude_code / codex / api / flash（不变） | — | — | — |
| 运行轴 | `run_mode`、`policy_mode`（tool / code，同一份工具声明）、`interactive`、`real_robot` | — | — | a_global 2.2、a_4 |
| Prompt 拼装 | 片段库、`assemble_prompt`、`effective_prompt.md` + sha256 | — | 领域片段（两种调用模式共用） | a_2 |
| 工具 | `Toolkit`（并发、取消、校验、finish 策略）、四层 `ToolResult`；Scene / Motion（+`vla_act`）/ Memory / File 四个族；Episode 会话（不确定态锁存、自动对账） | `toolkits/<name>/`：重实现与独立评估 | skill binding、原生特有工具、判据阈值配置 | a_3、a_6、a_7 |
| 环境接入 | `rpent/env/`：契约、`BaseEnvClient`、`BaseEnvFacade`、`ReceiptLedger`、`EpisodeSession`、`rpent.env.serve`、`SingleEnvView`（仅方案 b） | — | adapter、能力声明 | a_5、a_6 |
| 模型服务 | `rpent/robots/runtime.py`（进程拉起） | `capabilities/_base/` 与 `capabilities/<name>/` | 服务声明 | a_3 4.7、a_5 |
| 安装 | `rpent-env`、`require()`、安装指纹 | 每个组件的 `component.toml`；共用依赖 `envs/deps/*.toml`（如 `rlinf`） | `component.toml` | a_1 |
| 产物与外部交互 | `RunFinalizationContext`（run 级）；`run.json` / `result.json` / `transcript.json` / `events.jsonl`；`EventBus`，Dashboard 与 JSONL 是订阅者 | — | 真机 operator / HIL、Flash、数据导出 | a_7、a_8 |
| 验证 | 契约测试、故障注入、parity、`check_layout`、schema 快照 | 工具包的 `evaluation/` | 切片冒烟 | a_9 |

工具上下文（`EnvState` 的步历史、历史帧、产物引用）由 Toolkit 注入工具；Episode 会话状态（锁存、对账、操作员判定）不向工具暴露。运行结论由 `RunFinalizationContext` 在 run 级汇总，不随 episode 重建。

## 3. 模块对照

| 维度 | 改造前 | 改造后 | 文档 |
|---|---|---|---|
| 环境接入 | 每个切片写 3 层：rlinf_env / env_server / env_client | 核心 1 份 client + facade；切片只写 1 个 adapter | a_5 |
| 契约形状 | gym 形状，传原生 action 向量 | 语义命令 `PoseCommand` / `JointCommand` / `NativeChunk`，回执 `EnvReceipt` | a_5、a_6 |
| 观测 | 原生 obs 透传 | `CameraFrame` / `EnvSnapshot` 归一化，位姿统一指向 grasp site | a_5 |
| 进程拉起 | 每个 `robot_spec` 286–746 行 | 服务声明 + `runtime.py` 的三个函数；`spec.py` ≤80 行 | a_5 |
| 核心里的模型服务 | `rpent/robots/components/` 混放环境基类、模型基类和 8 个服务 | 环境基类进 `rpent/env/`，模型部分进 `capabilities/` | a_1 |
| 安装 | 单个 pyproject、14 个 extra、7 个继承、15 对手写冲突 | 组件清单 + 具名配方 + 安装指纹 | a_1 |
| 通用动作与感知 | 每种 3–7 份 | 1 份：轻量实现在 `rpent/tools/`，感知在工具包 | a_3 |
| 感知工具入口 | `segment`、`back_project`、`sample_world_xyz` 分开暴露 | 合并为 `geometry`，原语留在包内 | a_3 |
| 工具改动的证据 | 只能看 episode 是否成功 | 同一冻结语料上的 coverage 与误差前后对比 | a_3、a_9 |
| 原生技能 | 6 种写法，阈值是工具参数 | 模型服务 / skill binding / `vla_act` 三段，阈值在配置 | a_3、a_7 |
| 工具结果 | 单一 `data` 字典 | 四层：调用、执行、确定性、领域 | a_3 |
| 记忆访问 | 通用文件工具，可被 SDK 内置工具绕过 | Memory 族三工具，权限对所有写入路径生效 | a_3 |
| 物理写可靠性 | 传输失败等同执行失败，可能执行两次 | 回执、只在 `unknown` 时锁存、自动只读对账，at-most-once | a_6 |
| 成功口径 | 三处来源混用，评测模式下真值对模型可见 | 环境侧真值只来自 `adapter.evaluate()`，真机另有操作员判定通道，结果记 `truth_source`；都按 `run_mode` 过滤；退出码 0 / 1 / 75 | a_7 |
| Prompt | 每个切片一棵大树，合计约 3.0k 行 | 片段 + 工具族贡献 + 领域片段，约 1.2k 行 | a_2 |
| 运行产物 | transcript 追加写，没有 manifest | manifest、单对象 transcript、一个目录一次运行、单一事件总线 | a_8 |
| 验证 | 97 个按模块组织的测试 | 加上契约、故障注入、parity、`check_layout` | a_9 |
| 代码策略模式 | 切片各写一份 prompt（共 794 行），无记忆，教模型读真值 | 核心唯一接入，切片零改动，有记忆，真值隔离 | a_4 |
| 迁移开关 | — | 只有 `env_contract` 一个，迁移完成后删除 | a_global 5.3 |

## 4. 目录设计

完整的名字与路径以 a_global 2.1 为准，组件骨架以 a_1 4.2 为准；本节只列新增或改变角色的文件，不复制唯一表。

| 位置 | 新增 / 修改 | 文档 |
|---|---|---|
| `rpent/env/` | `contracts.py`、`client.py`、`facade.py`、`ledger.py`、`episode.py`、`serve.py`；`single_env.py`（仅方案 b） | a_5、a_6 |
| `rpent/tools/` | `{scene,motion,memory,file}_tools.py`、`motion/`（执行器、`vla_act`）；修改 `base.py`、`toolkit.py` | a_3、a_7 |
| `rpent/prompt/` | `assembly.py`、`fragments/*.md`；`code_policy.py` 作为 `policy_mode` 片段 | a_2、a_4 |
| `rpent/evaluation/`、`rpent/artifacts/` | `result.py`；`manifest.py`、`events.py` | a_7、a_8 |
| `rpent/cli/`、`rpent/install.py` | `rpent-env`、`require()` | a_1 |
| `capabilities/` | `_base/` 与各模型服务；由 `rpent/robots/components/` 的模型部分迁入 | a_1、a_3 4.7 |
| `toolkits/` | 首个是 `geometry/` | a_3 |
| `robots/<name>/` | `prompts/` 取代 `prompt_bundle.py`；新增 `adapter.py`、`skills/`、`native_tools.py` | a_1、a_5 |
| `envs/`、`scripts/` | 配方、`deps/`、锁；`check_layout.py`、`gen_extras.py` | a_1、a_9 |
| `tests/` | `unit_tests/contracts/`、`unit_tests/fault_injection/`、`unit_tests/toolkits/`、`parity/` | a_9 |

核心的 `RobotSpec` 与进程拉起仍留在 `rpent/robots/runtime.py` 和 `rpent/robots/robot_spec.py`；S2 只把切片侧的 `robot_spec.py` 改名为 `robots/<name>/spec.py`。核心文件保留 `robot_spec.py` 名字，不改名为 `spec.py`，避免与切片入口同名。

**新机器人的最小接入清单**：`component.toml`、`spec.py`、`config.py`、`adapter.py`、`prompts/domain.py`，约 0.6–1.0k 行，全部计入接入部分；`skills/` 和 `native_tools.py` 按需添加。环境 client/server、工具调度、代码策略模式、产物、结果口径、prompt 通用段落、依赖组合都不需要写。

## 5. 切片改造前后

![单个切片改造前后](assets/slice_before_after.svg)

> 图源：[`assets/slice_before_after.svg`](assets/slice_before_after.svg)，以 RoboTwin 为例。

| 切片 | 基线 | 接入部分目标 | 保留的差异化功能 | 目标合计 |
|---|---|---|---|---|
| robotwin | 4.0k | ≤1.0k | — | 约 1.0k |
| robodojo | 3.5k | ≤1.0k | Flash 0.5k | 约 1.5k |
| libero | 6.4k | ≤1.2k | Flash 1.3k、记忆 hook 0.2k | 约 2.7k |
| robocasa | 4.5k | ≤1.2k | benchmark 评测 0.4k、记忆 hook 0.2k | 约 1.8k |
| franka | 3.8k | ≤1.0k | Flash 0.9k、标定相关感知 0.4k | 约 2.3k |
| dual_franka | 6.1k | ≤1.2k | HIL / verdict 1.5k、标定相关感知 0.5k | 约 3.2k |
| yam | 7.4k | ≤1.0k | 硬件租约、伺服、几何、恢复、operator 3.5k | 约 4.5k |
| **合计** | **35.7k** | **约 7.6k** | **约 9.4k** | **约 17k** |

两列相加就是切片的全部代码，没有不计入的文件。仿真切片收敛得最彻底；真机切片的运营与安全逻辑和具体机器人强相关，只去掉其中的重复工具和样板代码。三套 Flash 实现的合并不在本轮范围内。

## 6. 代码量与文件量估算

### 6.1 核心 `rpent/` 的变化

| 模块 | 文件变化 | 行数变化 | 文档 |
|---|---|---|---|
| 模型部分迁出到 `capabilities/` | −27 | −4.1k | a_1 |
| `rpent/env/`：`contracts.py`、`ledger.py`、`serve.py`、`single_env.py`；`client.py` / `facade.py` 迁入后修改；`RpcFacade` 钩子 | +4 | +1.0–1.3k | a_5、a_6 |
| 四个族 + `motion/`（执行器、`vla_act`）；`base.py`、`toolkit.py` 修改 | +6 | +1.3–1.7k（大部分从切片上移） | a_3、a_7 |
| `evaluation/result.py` 修改 | 0 | +0.15–0.2k | a_7 |
| `prompt/assembly.py`（另有 6 份 `.md` 片段，约 0.3k 行） | +1 | 约 +0.1k | a_2 |
| `artifacts/` | +2 | +0.25–0.3k | a_8 |
| `cli/env.py`、`install.py` | +2 | +0.4–0.6k | a_1 |
| 现有模块的其他修改（cli、planner、code_policy 接入点） | 0 | 约 ±0.3k | 各篇 |
| **合计** | **−12** | **约 −0.4k**（迁出 −4.1k，新增 +3.7k） | |

### 6.2 全部 Python 源码

| 区域 | 基线 | 目标 | 说明 |
|---|---|---|---|
| `rpent/` | 18.1k / 83 | 约 17.7k / 约 71 | 6.1 |
| `capabilities/` | —（在 `rpent/` 里） | 约 4.1k / 约 27 | 由 `rpent/robots/components/` 迁入，只放模型服务 |
| `robots/` | 35.7k / 125 | 约 17k / 约 50 | 第 5 节 |
| `toolkits/` 实现 | — | 约 2.8k / 约 8 | `geometry`，新增的感知能力（参照 #341） |
| **合计（不含评估）** | **53.8k** | **约 41.6k** | **−12.2k（−23%）** |
| `toolkits/*/evaluation/` | — | 约 2.6k / 约 7 | 换来可重放的感知质量基线 |
| **合计（含评估）** | **53.8k** | **约 44.2k** | **−9.6k（−18%）** |
| `robots/` 占比（不含评估） | 66% | 约 41% | |
| 测试文件 | 97 | 约 132 | +35：契约约 14、故障注入约 6、parity 约 3、工具族约 5、工具包快速检查约 4、安装与布局约 3 |
| 新增测试代码 | — | 2–3k 行 | |

**重复代码的减少** 体现在 `robots/` 的 −18.7k；`capabilities/` 是搬家，不增不减；`toolkits/` 是新增能力和它的证据，不是重复代码。

**PR #340 单独计算**：它给核心新增约 0.84k 行、5 个文件，给切片新增 794 行 prompt。a_4 完成后，切片里的这 794 行降为 0，核心部分保留。

### 6.3 阶段性变化（不含评估）

| 时点 | `rpent/` | `capabilities/` | `robots/` | `toolkits/` | 合计 |
|---|---|---|---|---|---|
| 基线 | 18.1k | — | 35.7k | — | 53.8k |
| 第一批完成（搬迁、契约、回执、安装 P1–P2，RoboTwin 试点） | 约 15.7k | 约 4.1k | 约 33.0k | — | 约 52.8k |
| 第二批完成（工具族、真值，仿真切片迁完） | 约 17.4k | 约 4.1k | 约 23k | 约 2.8k | 约 47.3k |
| 全部完成（含真机切片、prompt、产物） | 约 17.7k | 约 4.1k | 约 17k | 约 2.8k | 约 41.6k |

以上都是设计阶段的估算。每批完成后，按 a_global 5.1 的口径重新统计并校准。

## 7. 改造成本与批次

| 批次 | 内容 | 规模（估） | 完成标志 |
|---|---|---|---|
| 1 契约、结构与可靠性 | a_1 S1–S2 与 P1–P2、a_5 P0–P2、a_6、a_9 基础设施 | 约 6–7 个 PR | 3 个试点配方可检查、可安装；RoboTwin 只靠 adapter 跑通；故障注入下重复执行次数为 0 |
| 2 工具与口径 | a_3、a_7，以及仿真切片迁移 | 约 8–10 个 PR | 切片里的通用动作为 0；感知工具只有一个入口；80-case 工具评估可重放 |
| 3 提示词、代码模式与产物 | a_2、a_4、a_8、a_5 P3 | 约 6–8 个 PR | prompt 行数达标；代码模式下切片零改动；每次运行都有 manifest |
| 4 真机切片与收尾 | yam、franka、dual_franka 迁移；a_1 S3、P3–P5 | 每个切片约 2 个 PR | 回执、锁存和门控行为与迁移前一致；`check_layout` 的 K1–K6 为 error，K7 保持 warning |

**代价**：

- 核心新增约 3.7k 行、15 个文件，同时迁出 4.1k 行模型代码；
- 工具包和评估语料需要持续维护，语料变更要走版本；
- 迁移期新旧路径并存；
- 新贡献者需要先读 a_global 第 2–4 节，以及本文第 4 节的接入清单；
- 切片能自由发挥的空间变小，新能力要么进工具包，要么通过 R7 审查。

## 8. 明确舍弃的设计

| 舍弃项 | 原因 |
|---|---|
| 按资源调度与后台作业（job 工具） | env 是单进程，写调用本来就串行；真正的并发点已经是独立进程 |
| 跨 planner 的 `ContextPolicy` 抽象 | 三个 planner 里有两个由 SDK 管理上下文，只剩一个消费者 |
| telemetry 框架（span / metric） | `elapsed_s` 加事件时间戳已经够用 |
| 账本落盘 | 服务端重启后旧回执已与仿真或硬件状态脱钩，落盘给不出可信答案；未确认请求由 `events.jsonl` 记录 |
| 部分执行也锁存 | 服务端已给出确定的执行位置，锁存只会让取消变成整个 episode 报废 |
| 多个迁移开关和开关组合矩阵 | 只保留一个 `env_contract`，其余改动原地替换 |
| 切片里骨架生成的 `env_client.py` / `env_server.py` / `toolkit.py` | client/facade 已通用，薄子类只是新的样板；服务端由 `rpent.env.serve` 启动 |
| 单一 mode 枚举 | 运行模式、调用模式、交互、实体是四条独立的轴（a_global 2.2） |
| 重要性分档、抽象形态分类、组件稳定度标签、代码 banner 规范 | 没有两个使用方，也没有机器检查的落点（R7） |
| 语义地图、向量检索、agent 可调用的 `forget` | 目前没有使用方；遗忘交给合并规则和人工审阅 |
| 暴露给模型的 reconcile 工具 | 由框架自动对账即可，不增加模型需要理解的概念 |
| `rpent reproduce` 命令 | manifest 已经足以人工复现，有真实需求时再加 |
| provider 继承体系、模板 DSL、FastAPI 服务化 | Protocol 加注册表、Python 树、现有 RPC 已经够用 |
| 统一的工具 benchmark 平台 | 每个工具包的 `evaluation/` 目录足够；只在需要比较时共享语料格式 |
| 把评估语料和原始数据放进源码树 | 仓库只保留固定清单与报告；RGB-D、mask、预测留在外部运行目录 |
| 按 extra 拆成多个 PyPI 发行包 | 冲突在环境解析，不在发行元数据；多包仍要逐环境解析，还会引入版本漂移 |
| 运行时自动安装依赖 | 不可复现，且会在 GPU 机器上产生未记录的环境变化 |

## 9. 怎样判定改造成功

不看总行数，看以下九条：

1. 新增一个仿真机器人，只改 `robots/<name>/` 一个目录，接入部分不超过 1.2k 行；
2. 切片里没有 `env_client.py` / `env_server.py` / `toolkit.py`，找不到 `move_to`、`set_gripper`、`view_env_state` 的本地实现；
3. 一次超时不会导致同一个动作执行两次，运行中能通过对账恢复；取消一个动作块后 episode 可以继续；
4. 评测模式下，无论 tool call 还是代码模式、是否开 Dashboard，模型都看不到真值字段；
5. 只凭产物目录，就能回答「跑了什么、模型看到了什么、结果是否可以接受」；
6. 任意已注册的工具不需要额外包装，就能以 `robo.<tool>(**kwargs)` 调用，返回与 tool call 一致；
7. 用 SDK 内置工具写记忆目录会被拒绝，佐证会参与记忆合并；
8. 改一个感知工具的参数或算法，不改任何切片，就能在同一冻结语料上看到 coverage 与误差的前后对比；
9. 在新机器上只凭一个具名配方装出环境，`rpent-env doctor` 通过；缺组件时错误信息直接给出配方，`run.json` 能追到安装指纹。
