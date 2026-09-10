# 复现问题记录：YAM / BEHAVIOR 适配改动

- **复现目标**：`feature/yam` 工作区相对 `main` (24541d6) 的 yam/behavior 适配改动中**非 env/vla 的工程部分**。
- **环境**：macOS arm64；micromamba python 3.11.16（`venv/`）；所有 pip 走清华镜像（`-i https://pypi.tuna.tsinghua.edu.cn/simple`）；git 走 ghfast.top 镜像（`~/.gitconfig` 已配置）。
- **日志**：`log/`（`check_imports.py`、`requirements-dev.txt`、`test_*.log`）。

---

## 一、复现流程

1. `micromamba create -p ./venv python=3.11 pip -y`
2. `./venv/bin/pip install -e . --no-deps`（见 P1：全量 `-e .` 会因 openai-codex 失败）
3. `./venv/bin/pip install -r log/requirements-dev.txt -i <清华镜像>`（numpy/pytest/omegaconf/gymnasium/pydantic 等）
4. `./venv/bin/pip install prompt-toolkit mcp claude-agent-sdk huggingface_hub anthropic mujoco==3.3.0`
5. `PYTHONPATH=<repo> ./venv/bin/python -m pytest tests/unit_tests/ tests/yam/`

> 注意：`robots/` 是 repo 根的顶层包（editable install 的 `[tool.uv] pythonpath=["."]` 只对 uv 生效），pytest/脚本必须带 `PYTHONPATH=<repo>` 才能 import `robots.*`。

## 二、问题清单

### P1 [环境/镜像] `openai-codex>=0.1.0b3` 在清华镜像不可得
`pip install -e .` 因解析不到 `openai-codex` 直接失败（`No matching distribution found`），导致 rpent 核心依赖无法整体安装。
- 处理：改用 `--no-deps` 装 editable 本体，再手动装其余核心依赖。
- 影响：`rpent/planner/codex.py`（codex planner）不可用；`tests/unit_tests/rpent/planner/test_codex_contracts.py` 无法收集（`ModuleNotFoundError: openai_codex`）。
- 判断：镜像/包可用性问题，非 PR 代码问题。若需完整复现 codex planner，需从官方 PyPI 或 ghfast.top 镜像获取 openai-codex。

### P2 [环境/镜像] `pyrealsense2` 在清华镜像不可得
- 影响：`tests/yam/test_projection.py::test_world_from_depth_rejects_modified_brown_conrady_deprojection` **失败**（`RuntimeError: Install pyrealsense2 ...`），另有 4 个 projection 测试 skipped。
- 判断：pyrealsense2 是 YAM 真实相机（RealSense）的绑定，属 yam 真实环境依赖；`robots/yam/cameras.py:117-120` 有清晰的缺失报错，`docs/yam/ACCEPTANCE.zh-CN.md:51` 也列出其版本。**公开安装说明未单独列出该依赖**（yam 无公开 usage 文档，仅内部 `docs/yam/`），可视为轻微 doc 遗漏，但非代码 bug。
- 备注：该测试对 pyrealsense2 有硬依赖，无 RealSense 环境的 CI 会一直红。

### P3 [环境] 缺 `mujoco` 时 tests/yam 大量 skipped
- 影响：`test_actual_model_geometry.py` 与 `test_path_guard.py` 的碰撞 guard 测试全部 skip（`could not import 'mujoco'`）。装 `mujoco==3.3.0`（pyproject 固定版本）后全部通过。
- 判断：纯环境问题，装上即过。

### P4 [环境] 缺 `anthropic` 包
`pydantic-ai-slim` 的 anthropic provider 是可选组（`pip install "pydantic-ai-slim[anthropic]"`）。不装时 `tests/unit_tests/rpent/planner/test_api_contracts.py` 4 个用例因 `ImportError: Please install the anthropic package` 失败。装上后全过。判断：环境问题。

### P5 [环境] `rlinf` 依赖不可得（env/vla 后端，按目标可跳过）
`tests/yam/test_runtime_dispatch.py` 4 个用例 skip（`could not import 'rlinf.envs.realworld.yam.i2rt_backend'`）。rlinf 是 YAM env 后端（`rpent[rlinf]` extra），属 env/vla 部分，本次复现按目标跳过。若需验证 runtime dispatch 需安装 RLinf。

### P6 [PR 相关，已升级至 review.md] `tests/yam` 与 unit_tests 未覆盖 behavior.toolkit
复现中发现 `import robots.behavior.toolkit` 直接 `ImportError`（`ToolResultEvent` 不存在）。现有测试（registry contracts、tests/yam、unit_tests）**都不触发该 import**，因此测试全部通过而 behavior 实际无法运行。→ 见 `review.md` H1。这是"测试覆盖缺口 + 真实 bug"双重问题：建议为 behavior toolkit 加一个 import/构建冒烟测试。

### P7 [流程] 未提交工作区内建 venv
`venv/`、`log/`、`review.md`、`problems.md` 均在 `rpent_yam_new`（git 仓库）内、未 commit；`venv/` 是 untracked 大目录，建议确认 `.gitignore` 是否已忽略（`git status` 会显示 `?? venv/`）。

---

## 三、验证通过的项
- `tests/unit_tests/`：256 passed, 3 skipped（缺 openai_codex/anthropic 之外的依赖所致；含 CLI `--explore` 泛化、registry 契约、http_mcp_server 图片传输新测试）。
- `tests/yam/`：114 passed（geometry / projection 针孔路径 / cli_routing / path_guard 非 mujoco 部分 / facade_vla_fake_integration 全部通过）。
- yam 与 behavior 的 robot_spec / runtime 契约（`supports_exploration`、`default_memory_profile`、dashboard metadata、memory 组件）与测试断言一致。
