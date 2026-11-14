# RPent 改造全局规范
> 状态：草案｜基线 `01e9cb3`｜最后更新 2026-11-14

本文件是改造系列的共同底座，包含术语与路径、运行轴与身份、分层职责、规则、开关、验收口径和文档地图。各主题文档只引用这里的条目，不再重复；**名字和路径以 2.1 节为唯一来源**，主题文档与之冲突时以本节为准。

- **基线**：RPent `main` `01e9cb3`；URA（uni-robot-agent）`852518e`；代码策略部分以 RLinf/RPent PR #340（open）为参照。
- **基线规模**（口径见第 5 节）：`rpent/` 18.1k 行 / 83 个文件（其中 `rpent/robots/components/` 4.4k 行 / 29 个文件），`robots/` 35.7k 行 / 125 个文件，测试 97 个。

## 1. 改造要解决什么

一句话：**RPent 以「机器人」为封装单位，于是每接一个机器人都要把整条栈重铺一遍；改造要把封装单位换成「能力」**。

| 症状 | 证据（基线） | 主题文档 |
|---|---|---|
| 切片太大，接入成本高 | 单切片 3.5k–7.4k 行；URA 同一个 RoboTwin 只有 227 行 | a_5 |
| 通用动作复制多份 | `move_to` 在 6 个文件定义，`view_env_state` 7 个，`rotate_wrist` 5 个，`back_project` 4 个 | a_3 |
| 工具无法单独评估 | 改阈值、点选或拟合只能看整段 episode 是否成功；`segment` / `back_project` 在 4–5 个切片各有实现，没有共同基线 | a_3、a_9 |
| 组件依赖和安装没有边界 | 14 个 extra、7 个继承、15 对手写冲突；安装说明分散在 16 个页面 | a_1 |
| 物理动作可能执行两次 | RPC 失败无法区分「没执行」与「执行了但回执丢了」 | a_6 |
| 评测真值泄露给模型 | `pi0_pick` 返回 `terminated`，`get_env_state` 提示「call finish with success」 | a_7 |
| prompt 按切片复制 | 切片 prompt 合计约 3.0k 行，记忆协议每个切片写一遍 | a_2 |
| 运行不可复现 | transcript 追加写，没有 run manifest | a_8 |
| 设计会慢慢退化 | 测试按模块组织，没有契约测试和架构检查 | a_9 |
| 新调用模式继续按切片复制 | PR #340 的代码模式给 7 个切片各加一份 prompt，共 794 行 | a_4 |

## 2. 术语、路径与身份

### 2.1 名词与路径（唯一表）

| 概念 | 唯一名字 | 路径 | 说明 |
|---|---|---|---|
| 切片 | slice | `robots/<name>/` | 一个机器人或仿真的实现 |
| 环境契约 | `EnvMeta`、`EnvSnapshot`、`CameraFrame`、`ArmState`、`PoseCommand`、`JointCommand`、`NativeChunk`、`EnvReceipt` | `rpent/env/contracts.py` | 跨进程数据类型，无 I/O，不依赖工具层（a_5、a_6） |
| 环境 client / facade | `BaseEnvClient` / `BaseEnvFacade` | `rpent/env/client.py` / `facade.py` | 由 `rpent/robots/components/env_{client,facade}_base.py` 迁入；全仓各一份，切片不再子类化 |
| 回执账本 | `ReceiptLedger` | `rpent/env/ledger.py` | 由 `BaseEnvFacade` 持有；`RpcFacade` 只提供写方法登记与分发钩子 |
| 环境契约异常 | `RequestRejected` / `ExecutionUncertain` | `rpent/env/contracts.py` | `RequestRejected` 只能在第一次原生调用前抛出，映射为 `rejected`；`ExecutionUncertain` 在传输失败时由 `BaseEnvClient` 抛出，携带 `request_id` 与 `sequence`，映射为 `execution_uncertain=True`（a_6） |
| Episode 会话 | `EpisodeSession` | `rpent/env/episode.py` | 保存 `episode_id`、不确定态锁存（`uncertain` / `uncertain_requests`）与操作员判定；由 `BaseEnvClient` 在 reset 时创建，不向工具暴露（a_6、a_7） |
| adapter | `<Name>Adapter` | `robots/<name>/adapter.py` | 原生 ↔ 契约翻译（a_5） |
| adapter 方法 | `describe` / `reset` / `step_pose` / `step_joints` / `step_native` / `read_state` / `capture` / `evaluate` / `close` | 同上 | `describe() -> EnvMeta` 是环境能力的唯一来源；`evaluate()` 是环境侧真值的唯一通道（a_5 4.2、a_7 4.2） |
| 单环境视图 | `SingleEnvView` | `rpent/env/single_env.py` | 方案 (b) 才有；把 adapter 传入的 RLinf 批量 Env 包成单环境，**不 import rlinf**（a_5 4.3） |
| 工具结果 | `ToolResult` | `rpent/tools/base.py` | 模型可见的四层结果；由 `EnvReceipt` 映射而来，环境层不依赖它（a_3） |
| 工具族 | Scene / Motion / Memory / File 族：`SceneTools` / `MotionTools` / `MemoryTools` / `FileTools` | `rpent/tools/{scene,motion,memory,file}_tools.py` | 拥有**模型可见的公共面**：工具名、schema、prompt 段、族级结果字段；按能力装配 |
| 工具包 | `toolkits/<name>/` | `toolkits/<name>/` | 需要独立评估语料的重实现（首个是 `geometry`）；族引用它，它不 import 族或切片 |
| 轻量工具实现 | — | 族文件旁，如 `rpent/tools/motion/` | 确定性动作、文件、记忆访问；评估用契约测试 |
| Toolkit | `Toolkit` | `rpent/tools/toolkit.py` | 调度器：并发、取消、校验、finish 策略；「Toolkit」只指它，`toolkits/` 只指工具包目录 |
| 模型能力 | `BaseAMClient` / `BaseVLAClient` / `BaseWAMClient` / `BaseAMFacade` | `capabilities/_base/` | 由 `rpent/robots/components/am_*` 迁入 |
| 模型服务 | `capabilities/<name>/` | `client.py`、`server.py`、`adapter/{encode,decode}.py` | **模型原生** I/O：契约输入 ↔ 模型张量；与机器人无关 |
| 技能绑定 | `SkillBinding` | `robots/<name>/skills/<skill>.py` | **机器人侧**：VLA/WAM 技能的观测 → 能力契约输入、动作块 → `NativeChunk`、工具参数 schema、子目标判据 `judge`（阈值来自配置） |
| 技能执行循环 | `vla_act` runner | `rpent/tools/motion/vla_act.py` | 采集 → binding → 推理 → binding → 逐块执行 → `judge` → 存档；不解释判据 |
| 组件清单 | `component.toml` | 每个 `robots/`、`toolkits/`、`capabilities/` 组件目录；只含依赖的组件为 `envs/deps/<name>.toml`（`kind = "deps"`） | 安装期依赖、探针、冲突（a_1）。**「组件」只指可安装单元**，进程拉起叫「服务」 |
| 环境配方 | `envs/<profile>.toml` | `envs/` | 受支持目标的唯一安装入口；配方名带后缀（`-sim`、`-real`、`-pro`），不与组件同名 |
| 安装指纹 | `rpent-install.json` | `<venv>/` | 安装证据；`run.json` 引用它 |
| 结果契约 | `RunFinalizationContext` | `rpent/evaluation/result.py` | 运行结论（a_7） |
| 运行清单 | `RunManifest` | `rpent/artifacts/manifest.py` | `run.json`（a_8） |
| 事件 | `EventBus`、`EventSink`（Protocol）、`JsonlEventSink`、`DashboardEventSink` | `rpent/artifacts/events.py`、`rpent/dashboard/events.py` | 一个总线、多个订阅者（a_8） |
| Prompt 拼装 | `assemble_prompt` | `rpent/prompt/assembly.py`、`rpent/prompt/fragments/*.md` | 「拼装」，不叫「编译」（a_2） |

其余术语：

| 术语 | 含义 |
|---|---|
| **能力声明** | 环境与服务能力的只读快照（`execution_capabilities`）：臂、相机、深度、标定、分割、策略后端、是否真机；决定暴露哪些工具和参数 |
| **回执** | 服务端对一条写请求的执行结论：执行了没有、执行到哪一步 |
| **对账** | 按 `request_id` 只读查询回执；**永不重放动作** |
| **不确定态** | 可能执行了但无法确认；锁存后拒绝所有写操作 |
| **真值** | 任务成功判定；环境侧来自 `adapter.evaluate()`，真机还可以来自操作员判定（a_7 4.2） |
| **片段** | 可复用的 prompt 段落，带来源 |
| **原生差异** | 只对某个原生环境成立的处理，留在切片，文件或函数注释以 `Native difference:` 开头 |

### 2.2 运行轴与身份

运行配置是四条**互相独立**的轴，不合并成一个 mode：

| 轴 | 取值 | 决定什么 | 来源 |
|---|---|---|---|
| 运行模式 `run_mode` | `evaluate` \| `explore` | finish 策略、真值是否对模型可见、能否 reset | CLI |
| 调用模式 `policy_mode` | `tool` \| `code` | 模型如何调用同一批工具 | CLI（a_4） |
| 交互 `interactive` | `false` \| `true`（Dashboard） | 暂停、恢复、operator 指令；**不改变真值可见性** | CLI |
| 实体 `real_robot` | `false` \| `true` | 真机安全片段、operator 门控 | 能力声明，不由 CLI 指定 |

身份只有四个：

| 身份 | 范围 | 分配者 |
|---|---|---|
| `run_id` | 一次 CLI 运行（一个输出目录） | CLI |
| `episode_id` | 一次 reset 到下一次 reset；explore 每个 attempt 一个 | `BaseEnvClient.reset()` |
| `request_id` | 一条写请求 | `BaseEnvClient` |
| `sequence` | 写请求在 episode 内的单调序号，reset 后从 0 开始 | `BaseEnvClient` |

工具调用另有 `tool_call_id`（planner 分配），代码模式另有 `cell_id`；二者只用于关联，不参与执行语义。

## 3. 分层职责

```
Planner（claude_code / codex / api / flash）
  │  调用模式：tool call │ code policy（同一工具声明）
Prompt 拼装 ── 片段库 + 工具族贡献 + 领域片段
工具与工具上下文 ┬─ Toolkit ───── 调度（readonly 并发 / 写者优先）· finish 策略 · 工具上下文（EnvState）
                 ├─ 工具族 ────── Scene / Motion(+vla_act) / Memory / File：公共面与装配
                 ├─ 工具包 ────── toolkits/<name>/：重实现 · 独立评估
                 └─ Episode 会话 ── 不确定态锁存 · 自动对账
  │  语义命令（PoseCommand / JointCommand / NativeChunk）→ EnvReceipt
BaseEnvClient ─ 身份 · 自动对账 · 回执 → ToolResult  ┐
  │  RPC（HTTP JSON / socket）                       ├ 核心，全仓一份
BaseEnvFacade ─ 路由 · 生命周期 · ReceiptLedger     ┘
  │
adapter ─────── 原生翻译                               ┐
skill binding · 能力声明 · 领域片段                    ├ 切片
原生仿真 / 真机 / 运营与安全逻辑                       ┘
capabilities/<name>/ ─ 模型服务（与机器人无关）
结果与产物 ── RunFinalizationContext（run 级）· RunManifest · EventBus

安装边界 ── component.toml（组件）→ envs/<profile>.toml（配方）→ rpent-install.json（指纹）
```

**判断代码归属**：

- 对两个以上机器人都成立的逻辑，不属于切片；
- 只对某一个原生环境成立的逻辑，属于切片，并标为**原生差异**。

## 4. 规则

所有规则写进 `AGENTS.md` 和 review checklist。可机器检查的部分由 `check_layout`（R1 的工具名部分、R2、R8、K4 的 import 边界，a_9）和 `rpent-env check`（R12，a_1）执行，其余由评审核对。

| 编号 | 规则 | 要点 |
|---|---|---|
| **R1** | 一种能力只实现一份 | 通用动作、感知、环境 client/facade、记忆协议、输出格式全仓各一份。要保留第二份，必须写明它是**原生差异**，或说明契约 / 生命周期 / 失败语义不同（见 R7） |
| **R2** | 切片只做翻译 | 切片负责：原生 → 契约、能力声明、技能绑定与判据、领域知识、原生特有工具、差异化功能。切片不负责：模型可见的通用工具、调度、通用 prompt、产物布局、评测口径 |
| **R3** | 物理写操作可识别 | 每条写请求带 `episode_id`、`request_id` 和 `sequence`；重复请求返回已有回执；丢失回执不等于失败，也不允许重放 |
| **R4** | 区分未执行与不确定 | 工具结果显式区分四件事：调用是否有效、动作是否执行、执行是否确定、领域结果 |
| **R5** | 评测模式不暴露真值 | `evaluate` 下模型可以知道 episode 是否结束，但不知道是否成功；`explore` 可以暴露真值，但必须标记 |
| **R6** | 判据属于配置 | 成功阈值放在机器人或 benchmark 配置里，模型不能通过工具参数放宽 |
| **R7** | 共享要有两个使用方 | 新增核心模块、契约字段或共享实现时，PR 写明两个以上真实使用方，且它们的契约和失败语义一致；否则留在原处。**没有调用点的字段、开关和扩展点不进核心**。保留第二份实现时，按 R1 标明原生差异或契约 / 失败语义差异 |
| **R8** | 核心不出现机器人名 | 平台差异通过能力声明和切片配置表达 |
| **R9** | 运行可复现 | 每次运行都写出 `run.json`、`effective_prompt.md`、`tools.json`、`transcript.json`、`result.json`；缺任何一个，该运行不进评测统计 |
| **R10** | 迁移期旧路径可用 | 见 5.3：每个切片在 `env_contract=v2` 通过 parity 之前保留旧路径；其余兼容别名（改名 shim、生成的 extras）保留一个 release |
| **R11** | 共享工具自带评估 | 每个共享工具都有独立于 episode 的验证入口；有模型参与的感知工具必须以工具包为单位提供固定语料、独立参考和可重放报告；改动附同一语料的前后对比 |
| **R12** | 依赖随组件声明 | 根 `pyproject.toml` 只保留核心依赖；每个组件自带 `component.toml`；受支持目标只通过具名配方安装 |

## 5. 通用口径

### 5.1 代码行数

- 只统计 `.py` 文件，不含 `tests/` 和 `__init__.py`；`.md` 片段和 TOML 单独统计；
- **总表覆盖全部 Python 源码**：`rpent/`、`capabilities/`、`robots/`、`toolkits/`（实现与 `evaluation/` 分列）；搬迁的代码在新位置计入，不从统计里消失；
- 切片行数分成两部分报告，**两部分合起来等于切片全部代码**，没有不计入的文件：
  - **接入部分**：`spec.py`、`config.py`、`adapter.py`、`skills/`、`prompts/`、`native_tools.py`；
  - **差异化功能**：Flash、记忆策略 hook、benchmark 评测脚本、真机运营与安全（operator、硬件租约、伺服、恢复、标定）；
- 「≤1.2k 行」这类目标只约束**接入部分**。差异化功能不设压缩目标，只要求不重复实现。

### 5.2 测试分层

不新增顶层测试目录，沿用现有 CI：

| 层 | 位置 | 依赖 | 何时运行 |
|---|---|---|---|
| 单元 + 契约 | `tests/unit_tests/contracts/` | fake 实现，CPU | 每个 PR |
| 故障注入 | `tests/unit_tests/fault_injection/` | `FakeEnvServer`、`FakeRpcTransport` | 每个 PR |
| 工具包快速检查 | `tests/unit_tests/toolkits/<name>/` | 合成观测、fake model | 每个 PR |
| Parity | `tests/parity/` | scripted planner，不调 LLM | 每个迁移 PR |
| 工具评估 | `toolkits/<name>/evaluation/` | 冻结观测、独立参考 | 工具改动与 nightly |
| 安装 | `rpent-env check` / fresh venv | 清单检查用 CPU；fresh 安装用真实依赖 | 每个 PR / nightly |
| 端到端 | `tests/e2e_tests/`（现有） | 真实仿真 / GPU | nightly 与 release |

离线测试不能证明真机可用。真机只验证可判定的部分：回执、锁存、门控、配置校验，结果单独记录。

### 5.3 开关与运行配置

全系列**只有一个迁移开关**：

| 开关 | 取值 | 作用域 | 生命周期 |
|---|---|---|---|
| `env_contract` | `legacy \| v2` | 按切片 | 所有切片迁移完成后删除 |

`env_contract` 同时决定该切片用哪套工具：`legacy` 用切片原有工具，`v2` 用工具族。工具族只对接 v2 契约，不做双契约兼容；切片回退开关时一并回退到旧工具，所以切片的旧工具在它通过 parity 之前不删除。

其余改动原地替换，用 parity 测试和 git revert 兜底。以下属于运行配置，不是迁移开关：

- 2.2 节的四条运行轴；
- `--truth-visibility visible`：只在 `evaluate` 下用于口径校准实验，结果不进排行榜（a_7）。

兼容别名（改名后的转发 shim、由清单生成的 extras）不是开关，保留一个 release 后删除。

## 6. 文档地图与依赖

| 文档 | 一句话 |
|---|---|
| [a_0 建立文档纪律与评审闸门](a_0_建立文档纪律与评审闸门.md) | 规则单一来源、证据分级写进 PR，设计文档入库 |
| [a_1 仓库结构、组件边界与安装](a_1_仓库结构、组件边界与安装.md) | 目录即角色，同类组件同骨架；组件自带依赖清单，环境按具名配方组装，安装有指纹 |
| [a_2 拼装提示词](a_2_拼装提示词.md) | prompt 由片段库、工具族贡献和领域片段按固定层序拼装，并产出可追溯的产物 |
| [a_3 抽出共享工具族](a_3_抽出共享工具族.md) | 通用动作、感知、记忆和文件工具全仓一份，按能力装配；感知以工具包为单位独立评估；原生技能收敛为 skill binding |
| [a_4 统一代码策略调用](a_4_统一代码策略调用.md) | 代码模式只是同一批工具的另一种调用方式，不再给每个切片加一份 prompt |
| [a_5 精简机器人接入](a_5_精简机器人接入.md) | 用语义命令契约加 adapter 取代切片里的三层 RPC 拷贝，切片只做原生翻译 |
| [a_6 建立执行回执语义](a_6_建立执行回执语义.md) | 物理写请求可识别、可对账；不确定就停，永不重放 |
| [a_7 隔离任务真值](a_7_隔离任务真值.md) | 把三种成功分开；评测模式下真值不进入模型上下文；判据外置 |
| [a_8 统一运行产物](a_8_统一运行产物.md) | 每次运行一个 manifest，transcript 是单个对象，工具调用、step 和 RPC 可以 join |
| [a_9 建立验证护栏](a_9_建立验证护栏.md) | 把每条规则和验收条件变成测试、工具评估与 CI 检查 |
| [a_summary](a_summary.md) | 目标架构、模块对比、目录设计、代码量与文件量 |

**依赖关系**：

```
a_5 契约 ──┬──> a_3 工具族 ──┬──> a_2 提示词 ──┐
           │                 └──> a_4 代码策略 <┤
           └──> a_6 回执 ──> a_7 真值/结果 ─────┴──> a_8 产物
a_0 文档与证据：先于所有主题，规定规则写在哪、证据怎么留
a_1 结构与安装：S1–S2 先于所有主题（目录与骨架），安装 P1–P2 与第一批并行
a_9 护栏：贯穿每一步，每个主题的验收条件都映射到测试
```

**实施批次**（不必按编号顺序）：

1. **契约、结构与可靠性**：a_1 S1–S2（目录与 `capabilities/` 搬迁）与安装 P1–P2；a_5 P0–P2（RoboTwin 试点）；a_6 回执。a_5 与 a_6 共用 `rpent/env/contracts.py`，同步落地；
2. **工具与口径**：a_3 工具族（含感知工具合并与独立评估）加 a_7 真值隔离，仿真切片迁移，并给出口径校准报告；
3. **提示词、代码模式与产物**：a_2、a_4、a_8；
4. **持续进行**：a_9 的测试随每一批补齐；其余切片按 RoboTwin → LIBERO → RoboCasa / RoboDojo → 真机的顺序迁移。

**阅读顺序**：先读本文第 2–4 节，再读 [a_summary](a_summary.md) 的目标架构，然后读 [a_5](a_5_精简机器人接入.md) 和 [a_1](a_1_仓库结构、组件边界与安装.md)。其余文档按需阅读；动笔或开 PR 之前先看 [a_0](a_0_建立文档纪律与评审闸门.md)。
