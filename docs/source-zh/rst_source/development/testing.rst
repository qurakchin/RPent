测试与 CI
=========

RPent 的验证分为四层：离线 CPU 单元测试、仓库结构检查、仿真器环境构建（支持带缓存构建与从零冷安装）以及 GPU 端到端测试。本页介绍如何在 GitHub 上触发 CI、``tests/`` 的目录结构、接入新机器人或新模型时需要补充的测试，以及本地运行测试的方法。

在 GitHub 上触发 CI
-------------------

.. list-table::
   :header-rows: 1
   :widths: 28 32 40

   * - 工作流
     - 触发方式
     - 验证范围
   * - **单元测试与结构检查**
     - push 与 PR 自动触发
     - 离线 CPU 单元测试、覆盖率、打包检查与目录结构检查
   * - **仿真器环境构建**
     - **Actions → Run workflow** 或 PR 评论 ``/ci-build``
     - 在全新虚拟环境中安装各仿真组件（默认带缓存构建，加 ``no_cache`` / ``--no-cache`` 从零冷安装），并验证 ``rpent-install.sh doctor`` 与 ``rpent --help``
   * - **具身 GPU 端到端测试**
     - **Actions → Run workflow** 或 PR 评论 ``/ci-all`` / ``/ci-<target>``
     - 干净安装并运行仿真冒烟、模型组件与完整 CLI 端到端测试

仿真器环境构建
~~~~~~~~~~~~~~

PR 评论触发需要仓库维护者权限。

- **手动触发**：进入 **Actions → Simulator environment builds → Run workflow**，选择 ``component``\ （``all`` 或 ``robot-libero``、``robot-libero_plus``、``robot-robocasa``、``robot-robotwin``、``robot-robodojo``、``robot-robolab`` 之一），需要从零冷安装时勾选 ``no_cache``。
- **PR 评论**：评论 ``/ci-build``\ （或 ``/ci-build-all``）构建全部组件，或 ``/ci-build-<component>`` 构建单个组件；需要从零冷安装时在后面加上 ``--no-cache``。示例：

  - ``/ci-build``
  - ``/ci-build-robot-libero``
  - ``/ci-build-robot-libero --no-cache``

具身 GPU 端到端测试
~~~~~~~~~~~~~~~~~~~

PR 评论触发需要仓库维护者权限。

- **手动触发**：进入 **Actions → Embodied GPU E2E → Run workflow**，选择 ``target``\ （``all``、``libero``、``libero-pro``、``libero-plus``、``robocasa``、``robotwin``、``robodojo`` 或 ``robolab``）。
- **PR 评论**：评论 ``/ci-all`` 运行全部仿真套件，或评论 ``/ci-<target>`` 运行单个套件。示例：

  - ``/ci-all``
  - ``/ci-libero``
  - ``/ci-robocasa``

测试结构
--------

``tests/`` 包含三个顶层目录：

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - 目录
     - 职责
   * - ``tests/unit_tests/``
     - 离线 CPU 单元测试，无需 GPU、仿真器或模型权重。不启动真实服务，使用轻量级内存替代实现验证接口、配置解析、数据格式转换与进程清理。
   * - ``tests/tooling/``
     - 独立检查脚本，无需安装 Python 环境即可运行，用于校验目录结构、``component.toml`` 依赖清单与模块导入边界。
   * - ``tests/e2e_tests/``
     - GPU 端到端测试，启动真实仿真器与模型服务，包含公共辅助函数（``common.py``）与干净环境运行脚本（``run_gpu_suite.sh``）。

单元测试目录与源码目录保持对应：

.. list-table::
   :header-rows: 1
   :widths: 36 64

   * - 源码目录
     - 单元测试目录
   * - ``rpent/<module>``
     - ``tests/unit_tests/rpent/<module>/``
   * - ``robots/<name>/``
     - ``tests/unit_tests/robots/<name>/``
   * - ``components/models/<name>/``
     - ``tests/unit_tests/components/models/``
   * - ``components/tools/<name>/``
     - ``tests/unit_tests/components/tools/``
   * - ``component.toml`` 依赖清单
     - 由 ``tests/unit_tests/installs/`` 与 ``./tests/tooling/run.sh layout`` 自动校验

编写测试时遵循以下约定：

- 仅单个测试文件用到的辅助类与准备逻辑保留在当前测试文件内；多个测试文件共用的初始化逻辑再移至 ``conftest.py``。
- 测试文件按验证重点命名：``*_contracts.py`` 验证接口与配置，``*_loopback.py`` 验证本地端口或 HTTP 通信，``*_lifecycle.py`` 验证服务启停与清理，``*_smoke.py`` 验证基础启动流程。
- ``tests/unit_tests/rpent/install/`` 使用临时目录验证安装器自身逻辑；针对仓库内真实 ``component.toml`` 清单的校验放在 ``tests/unit_tests/installs/``。

新增机器人或模型所需测试
------------------------

接入新机器人或仿真环境
~~~~~~~~~~~~~~~~~~~~~~

在 ``robots/<name>/`` 下新增机器人（或同时在 ``components/sim/<name>/`` 下新增仿真器）时，需补充以下三部分：

1. **离线 CPU 单元测试**\ （位于 ``tests/unit_tests/robots/<name>/``）：

   - 验证机器人注册、CLI 参数、配置解析、Prompt 组装与工具定义。
   - 使用轻量级本地测试服务替代真实仿真器与模型，验证 CLI 执行、本地 RPC 通信与子进程正常退出。
   - 运行 ``./tests/tooling/run.sh layout`` 与 ``tests/unit_tests/installs/``，确认 ``component.toml`` 与导入边界通过校验。

2. **GPU 端到端测试**\ （位于 ``tests/e2e_tests/<name>/``，复用 ``tests/e2e_tests/common.py``）：

   - **环境冒烟**\ （``test_environment_smoke.py`` 或 ``test_components.py`` 中的环境用例）：仅依赖仿真资产与 GPU/EGL（不加载模型权重），验证环境启动、reset、基础动作执行、观测读取与正常关闭。
   - **模型组件**\ （``test_components.py``）：向模型服务发送真实仿真观测，获取预测动作并执行。
   - **完整 CLI 调用链**\ （``test_policy_chain.py``）：调用 ``run_scripted_policy_chain``，配合本地脚本化规划器（无需外部 LLM API）验证公开 CLI、输出文件与后台进程退出。

3. **接入 CI**：

   - 在 ``tests/e2e_tests/run_gpu_suite.sh`` 中新增 target，并注册到 **具身 GPU 端到端测试** 工作流。
   - 如新增了可安装的 ``robot-<name>`` 组件，同步注册到 **仿真器环境构建** 工作流。

完整的机器人接入步骤见 :doc:`add_robot`。

接入新模型
~~~~~~~~~~

在 ``components/models/<name>/`` 下新增动作模型或感知模型时，需补充以下三部分：

1. **离线 CPU 单元测试**\ （位于 ``tests/unit_tests/components/models/``，特定机器人的适配逻辑位于 ``tests/unit_tests/robots/<robot>/``）：

   - 验证配置校验、启动参数检查，以及 RPent 物理量与模型输入输出之间的格式转换。
   - 使用轻量级测试后端验证本地 HTTP/socket 通信，包括多会话隔离、reset、错误处理与 worker 正常退出。

2. **GPU 端到端用例**\ （加入对应机器人的 ``tests/e2e_tests/<robot>/``）：

   - 在 ``test_components.py`` 中补充真实推理与执行用例，在 ``test_policy_chain.py`` 中补充完整 CLI 调用链用例。
   - 使用 ``require_model_path``\ （或对应的解释器、endpoint 检查）守卫模型用例，缺少权重时仅跳过对应模型的用例，不影响整个仿真套件。

3. **接入 CI**：

   - 在 **具身 GPU 端到端测试** 工作流中配置该模型的权重、解释器或 endpoint 环境变量（暂缺的资源置为空字符串，使 CI 仅跳过对应用例）。

完整的动作模型接入步骤见 :doc:`add_action_model`。

本地运行测试
------------

本地运行离线测试
~~~~~~~~~~~~~~~~

安装 ``infra-unit_cpu``\ （包含模型服务单元测试所需的 CPU 版 PyTorch），再运行 pytest：

.. code-block:: bash

   ./rpent-install.sh install infra-unit_cpu --venv .venv-unit-cpu
   .venv-unit-cpu/bin/python -m pytest tests/unit_tests -v
   .venv-unit-cpu/bin/python -m pytest tests/unit_tests/robots/<name> -v

仓库结构检查无需激活虚拟环境，直接执行：

.. code-block:: bash

   ./tests/tooling/run.sh layout

本地运行 GPU 套件
~~~~~~~~~~~~~~~~~

在具备独立 NVIDIA GPU、EGL 以及对应资产和权重的机器上，传入两个不存在的输出目录与虚拟环境目录运行单个套件：

.. code-block:: bash

   export CUDA_VISIBLE_DEVICES=<单个物理 GPU 编号>
   export MUJOCO_GL=egl
   export PYOPENGL_PLATFORM=egl

   bash tests/e2e_tests/run_gpu_suite.sh \
     <target> \
     /path/to/new-output-dir \
     /path/to/new-venv-root

在已安装环境的机器上调试单个文件或用例时，可直接运行 ``pytest tests/e2e_tests/<robot> -v -k <expression>``。
