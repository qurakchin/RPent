安装
====

RPent 安装的是具名环境配方，而不是一组 extra。``envs/`` 中的每个配方选择组件及其放置方式，每个组件在 ``component.toml`` 中声明自己的依赖。``rpent-env`` 创建虚拟环境，只安装该配方的内容，对每个组件执行导入探针，并写入安装指纹。

环境要求
--------

- Linux ``x86_64`` 和 `uv <https://docs.astral.sh/uv/getting-started/installation/>`_。
- 配方指定的 Python minor 版本；本机没有时，``rpent-env`` 会让 uv 下载。
- 仿真器和真机配方需要与该配方的 PyTorch 构建兼容的 GPU 和驱动。

查看与检查配方
--------------

.. code-block:: bash

   rpent-env list
   rpent-env check --all

``check`` 读取清单和配方，计算 ``requires`` 闭包，报告放置方式冲突、重复锁定、不支持的 Python 版本和平台不匹配。它不会下载任何依赖。

安装配方
--------

在源码目录中把配方安装到虚拟环境：

.. code-block:: bash

   rpent-env install libero-pro --venv .venv
   source .venv/bin/activate

新检出的仓库还没有 ``rpent-env`` 命令。可以先不安装 RPent，直接引导它：

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.env install libero-pro --venv .venv
   source .venv/bin/activate

重复执行会复用环境并修复过期安装。配方有锁时安装器使用锁；``--dev`` 追加的测试依赖不在锁内，此时改用生成的 requirements 解析。``--dry-run`` 只打印生成的 requirements。配方把组件放到外部环境时，安装器会打印该环境的安装命令；请在同一个源码目录中执行。

配方
----

.. list-table::
   :header-rows: 1
   :widths: 28 10 62

   * - 配方
     - Python
     - 内容
   * - ``minimal``
     - 3.11
     - 仅核心 RPent，用于验证不安装扩展时的 CLI 和机器人发现。
   * - ``dev``
     - 3.11
     - 测试和 lint 依赖；可用 ``rpent-env install <配方> --dev`` 附加到其他配方。
   * - ``libero`` / ``libero-pro`` / ``libero-plus``
     - 3.11
     - 对应 LIBERO 变体，含 RLinf、Pi0.5 和 SAM 3.0。
   * - ``libero-pro-flywheel``
     - 3.11
     - LIBERO-PRO 与 LeRobot 轨迹导出。
   * - ``libero-pro-molmo``
     - 3.11
     - LIBERO-PRO，并将 Molmo 定位放在外部 ``molmo`` 环境。
   * - ``libero-openpi-external``
     - 3.11
     - LIBERO-PRO，通过 ``--am-endpoint`` 连接外部 ``openpi`` 环境中的 Pi0.5 服务。
   * - ``franka`` / ``dual-franka``
     - 3.11
     - Franka 真机；双臂配方额外包含 SAM 3.0。
   * - ``robocasa``
     - 3.10
     - RoboCasa365 与 RLinf 的 RoboCasa、RLDX 栈。
   * - ``robotwin``
     - 3.11
     - RoboTwin 与 LingBot-VLA、cuRobo。
   * - ``robodojo`` / ``robodojo-sim``
     - 3.11
     - RoboDojo 及其 RLinf fork 与 Isaac Sim 运行时。
   * - ``yam``
     - 3.11
     - YAM 控制和推理依赖。
   * - ``molmo``
     - 3.11
     - 独立的 Molmo 服务环境（``core = false``）。
   * - ``geometry-eval``
     - 3.11
     - 几何工具包及其冻结的 CPU 评测语料。
   * - ``rlinf`` / ``sam3`` / ``openpi`` / ``flywheel``
     - 3.11
     - 单能力诊断环境。

诊断与复现
----------

.. code-block:: bash

   rpent-env doctor --venv .venv
   rpent-env inspect --venv .venv
   rpent-env lock --all
   rpent-env lock --all --check

``doctor`` 将安装指纹与配方清单比较，检查 Python 和平台，运行 ``uv pip check`` 与组件探针，并可用 ``--endpoint molmo=host:port`` 探测外部 endpoint。``inspect`` 打印指纹及其 hash。``lock`` 用 ``uv pip compile`` 生成 ``envs/locks/<配方>.lock``；``--check`` 在锁过期时失败。Linux 锁默认以 ``manylinux_2_31`` 为基线（glibc 2.31，即 Ubuntu 20.04 或更新版本），因为当前 GPU wheel 不再为更早的基线发布。若组件需要更新的基线，配方可用 ``manylinux`` 提高它；例如 RoboDojo 为 Isaac Sim 5.1 的 wheel 使用 ``manylinux = "2_35"``。``lock --all`` 会报告在当前主机上无法解析的配方并继续处理其余配方；``robotwin`` 锁需要在设置了 ``CUDA_HOME`` 的 Linux 主机上生成，因为 cuRobo 在解析期间构建元数据。重新生成锁时使用较新的 ``uv``：旧版本对相同输入可能解析出不同版本，结果会与仓库中的锁不一致。

运行产物会在 ``run.json`` 中记录当前配方、指纹 hash、源码 commit 和组件名。

兼容 extra
----------

``scripts/gen_extras.py`` 根据同一组清单和配方生成 ``pyproject.toml`` 中的 ``[project.optional-dependencies]`` 和 ``[tool.uv].conflicts``。它们让 ``pip install -e ".[libero-pro]"`` 在一个发布周期内继续可用；不要手工修改该区块。``scripts/gen_extras.py --check`` 在区块过期时失败。受支持的接口是配方，extra 只用于迁移。

平台准备、checkpoint 和资产见各仿真器或机器人页面。
