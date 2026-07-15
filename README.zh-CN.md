<div align="center">
  <img src="docs/logo.png" alt="RPent" width="200"/>
  <h1>RPent：面向物理世界的智能体基础设施</h1>
</div>

<div align="center">

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red.svg)](README.zh-CN.md)
[![GitHub](https://img.shields.io/badge/GitHub-RPent-181717?logo=github)](https://github.com/RLinf/RPent)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](docs/README.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

</div>

<div align="center">
  <img src="docs/architecture.svg" alt="RPent 架构" width="960"/>
</div>

RPent（Recursive Physical Agent，递归式物理智能体）是一个开放的具身智能体框架，用于构建能够通过与物理世界的**递归交互**而持续进化的智能体。RPent 并不预设某一个基础模型，而是提供一个递归式智能体框架，将感知、推理、记忆、执行与自我进化等**异构智能**统一整合为一个具身智能体。通过持续的交互、反思与适应，RPent 让具身智能体不断获取新能力，超越其初始设计。

**Pent** 之名源自**五角星（Pentagram）**：五个顶点象征多模态智能融合为统一的具身智能体；其正中的无穷符号（**∞**）代表感知、推理、执行与自我进化的**无尽递归循环**——智能由此不断向物理世界扩展。

RPent 以**服务化（Service-oriented）、标准化（Standardized）、组合化（Composable）**为核心设计理念，将模型、机器人、技能、记忆与环境统一纳入智能体基础设施：通过**服务化**实现能力解耦，通过**标准化**实现生态连接，通过**组合化**实现智能重构，让具身智能系统能够像软件一样被构建、扩展和持续进化。这些原则让 RPent 超越传统机器人控制框架，成为一套**面向物理世界的智能体基础设施（Agentic Infrastructure for the Physical World）**——智能不仅在此被部署，更被持续构建、扩展与进化。

## 支持的环境

<table style="width: 100%; table-layout: auto; border-collapse: collapse;">
  <thead align="center" valign="bottom">
    <tr>
      <th style="text-align: left;">仿真环境</th>
      <th>VLA 策略</th>
      <th>决策大脑</th>
    </tr>
  </thead>
  <tbody valign="top">
    <tr>
      <td style="text-align: left; padding-left: 8px;">
        <ul style="margin-left: 0; padding-left: 16px;">
          <li><b>LIBERO</b>（standard / pro / plus）✅</li>
          <ul>
            <li>libero_object · _task / _swap / _lan</li>
            <li>libero_goal · _task / _swap / _lan</li>
            <li>libero_spatial · _task / _lan</li>
            <li>libero_10 · _task / _swap / _lan</li>
          </ul>
          <li><b>RoboCasa</b>（厨房长程任务）✅</li>
          <ul>
            <li>PickPlace* · Open/Close* · TurnOn/Off* …</li>
          </ul>
        </ul>
      </td>
      <td>
        <ul style="margin-left: 0; padding-left: 16px;">
          <li><b>Pi0.5</b>（LIBERO，HTTP）✅</li>
          <li><b>RLDX-1</b>（RoboCasa，socket-RPC）✅</li>
        </ul>
      </td>
      <td>
        <ul style="margin-left: 0; padding-left: 16px;">
          <li><b>api</b> —— pydantic-ai ✅</li>
          <ul>
            <li>Anthropic（Claude）✅</li>
            <li>OpenAI（responses）✅</li>
            <li>OpenAI 兼容（chat）✅</li>
          </ul>
          <li><b>claude_code</b> —— Claude Agent SDK ✅</li>
          <li><b>codex</b> —— OpenAI Codex SDK ✅</li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>

## 快速开始

RPent 依赖 [RLinf](https://github.com/RLinf/RLinf) 的一个 fork 分支来提供仿真器与 VLA 模型。请把两者并排 clone。

**1. 并排 clone RLinf 与 RPent。**

```bash
mkdir workspace && cd workspace
# RPent 依赖 RLinf 的 fork 分支；后续迭代稳定后会合并回 main。
git clone https://github.com/jx-qiu/RLinf -b feature/physicalagent rlinf
git clone https://github.com/RLinf/RPent rpent
```

**2. 在 RLinf 中创建 openpi + LIBERO 虚拟环境。**

```bash
cd rlinf
bash requirements/install.sh embodied --env libero --model openpi --use-mirror --venv ../.venv-opi-libero
cd ..
source .venv-opi-libero/bin/activate
```

**3. 在上述 venv 之上安装 RPent 的额外依赖。**

```bash
cd rpent
uv sync --active --inexact
bash scripts/install_libero_pro_plus.sh
```

**4. 配置密钥与 checkpoint，然后运行。**

```bash
# 大模型 API 密钥（api 决策大脑）
export ANTHROPIC_BASE_URL=https://xxx
export ANTHROPIC_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx
export OPENAI_API_KEY=sk-xxx

# VLA checkpoint —— 从以下地址下载：
# https://huggingface.co/datasets/RLinf/rlinf-pi05-libero-130-fullshot-sft
export PI05_CHECKPOINT_PATH=/path/to/rlinf-pi05-libero-130-fullshot-sft
export LIBERO_TYPE=pro
export CUDA_DEVICE=0

# 运行一个任务：libero_object_swap，task 2，seed 0，使用 api 决策大脑、
# 一个 Anthropic 模型，最大输出 8192 token。
#   • OpenAI 兼容 chat 端点：  --model openai-chat:glm-5.2
#   • OpenAI responses 端点：  --model openai:gpt-5.5
#   • claude_code / codex 大脑：无需 provider 前缀，如 --model claude-opus-4-8
python rpent/cli/main.py --suite libero_object_swap --task 2 --seed 0 \
  --cerebrum api --model anthropic:claude-opus-4-8 --max_tokens 8192
```

### 实时 Dashboard

加上 `--dashboard` 即可为本次运行打开一个浏览器监控页。它会先展示一个启动屏让你选择配置，然后实时推送推理流、实时画面与动作时间线。用 `--dashboard_language zh-cn` 切换到中文界面。

```bash
python rpent/cli/main.py --dashboard --dashboard_language zh-cn \
  --suite libero_goal_task --task 1 --seed 0 --cerebrum claude_code
```

### RoboCasa

RoboCasa 使用独立的入口与安装指南。

```bash
bash scripts/setup_robocasa.sh                                # 一次性安装
bash scripts/run_robocasa.sh PickPlaceCounterToCabinet 0 0    # <任务> <GPU> <种子>
```

完整的 RoboCasa365 + RLDX-1 部署流程见 [SETUP_ROBOCASA.zh.md](docs/SETUP_ROBOCASA.zh.md)。

## 主要命令行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--suite` | —（必填） | 任务集，如 `libero_object_task`、`libero_spatial_swap` |
| `--task` | —（必填） | 任务集内的任务编号 |
| `--seed` | `0` | 随机种子 |
| `--cerebrum` | `api` | 决策大脑：`api` \| `claude_code` \| `codex` |
| `--model` | — | 模型 id；`api` 需带 provider 前缀（`anthropic:…`、`openai:…`、`openai-chat:…`） |
| `--max_turns` | `100` | 智能体最大轮数 |
| `--max_tokens` | `8192` | 单次回复最大 token |
| `--max_episode_steps` | `600` | 环境最大步数（`libero_10` 自动提升到 5000） |
| `--libero_type` | 自动 | `standard` \| `pro` \| `plus`（由任务集后缀自动路由） |
| `--cuda_device` | `0` | env / vla server 使用的 GPU |
| `--dashboard` | 关 | 为本次运行启动本地 dashboard |
| `--dashboard_language` | `en` | Dashboard 界面语言：`en` \| `zh-cn` |
| `--vla_endpoint` | — | 复用已在运行的 vla_server，而非新起一个 |
| `--no-servers` | 关 | 连接已存在的 env_server / vla_server |

## 文档

- [接入新环境](docs/ADD_A_NEW_ENV.zh.md) —— 把新的仿真器 / 机器人接入 runner（[English](docs/ADD_A_NEW_ENV.md)）。
- [RoboCasa 安装](docs/SETUP_ROBOCASA.zh.md) —— RoboCasa365 + RLDX-1 安装与运行指南。
- [`docs/`](docs/README.md) —— 完整文档索引。

## 致谢

RPent 构建于 [RLinf](https://github.com/RLinf/RLinf) 的仿真器、VLA 模型与训练基础设施之上，也得益于更广泛开源社区的 agent SDK —— [pydantic-ai](https://ai.pydantic.dev/)、[Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) 与 OpenAI Codex SDK。感谢 LIBERO、RoboCasa、robosuite、MuJoCo、openpi 背后的团队。
