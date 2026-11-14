安装
====

RPent 安装的是具名环境配方，而不是一组 extra。``envs/`` 中的每个配方选择组件及其放置方式，每个组件在 ``component.toml`` 中声明自己的依赖。``rpent-env`` 创建虚拟环境，只安装该配方的内容，对每个在本地安装的组件执行导入探针，并写入安装指纹。

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

``check`` 读取清单和配方，计算 ``requires`` 闭包，报告放置方式冲突、重复锁定、不支持的 Python 版本、平台不匹配，以及已声明但不再覆盖当前依赖的锁。它不会下载任何依赖。加上 ``--resolve`` 后，它还会用 ``uv pip compile`` 编译每个通过上述检查的配方，确认声明的依赖可解；这与 ``lock`` 走同一条代码路径，会从配置的索引读取包元数据。

安装配方
--------

在源码目录中把配方安装到独立的虚拟环境：

.. code-block:: bash

   rpent-env install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

新检出的仓库还没有 ``rpent-env`` 命令。可以先不安装 RPent，直接引导它：

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.env install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

``rpent-env`` 需要在源码检出中运行。wheel 包含核心包、各组件包及其 ``component.toml``，而 ``envs/`` 只随仓库发布：非可编辑的 ``pip install rpent`` 提供 ``rpent`` 和组件代码，``rpent-env`` 会报告找不到配方。

每个配方使用自己的虚拟环境。不同配方锁定不同的仿真器、机器人和模型运行时，安装器会拒绝在已安装其他配方的环境中安装；请为它指定另一个 ``--venv``。不传 ``--venv`` 时，配方安装到源码目录下的 ``.rpent/venvs/<配方>``；``.rpent/`` 是本地状态、已被 git 忽略，之后的 ``install`` 和 ``doctor`` 会复用同一个环境。``core = false`` 的配方（例如 ``molmo-server``）不安装可编辑的 RPent，只包含该服务自己的依赖；启动时按 :doc:`../guides/flash` 的说明把源码目录放进 ``PYTHONPATH``。

重复执行会复用环境并修复过期安装。配方有锁时安装器使用锁，并先检查锁是否仍覆盖全部直接依赖；锁过期时会失败并给出重新生成的 ``rpent-env lock <配方>`` 命令。``--dev`` 追加的测试依赖不在锁内，此时改用生成的 requirements 解析。``--dry-run`` 只打印生成的 requirements。配方把组件放到外部环境时，安装器会打印该环境的安装命令；请在同一个源码目录中执行。

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
   * - ``libero-sim`` / ``libero-pro`` / ``libero-plus``
     - 3.11
     - 对应 LIBERO 变体，含 RLinf、Pi0.5 和 SAM 3.0。
   * - ``libero-pro-flywheel``
     - 3.11
     - LIBERO-PRO 与 LeRobot 轨迹导出。
   * - ``libero-pro-molmo``
     - 3.11
     - LIBERO-PRO，并将 Molmo 定位放在外部 ``molmo-server`` 环境。
   * - ``libero-openpi-external``
     - 3.11
     - LIBERO-PRO，通过 ``--am-endpoint`` 连接外部 ``openpi-server`` 环境中的 Pi0.5 服务。
   * - ``franka-real`` / ``dual-franka-real``
     - 3.11
     - Franka 真机；双臂配方额外包含 SAM 3.0。
   * - ``robocasa-sim``
     - 3.10
     - RoboCasa365 与 RLinf 的 RoboCasa、RLDX 栈。
   * - ``robotwin-sim``
     - 3.11
     - RoboTwin 与 LingBot-VLA、cuRobo。
   * - ``robodojo-sim``
     - 3.11
     - RoboDojo 及其 RLinf fork 与 Isaac Sim 运行时。
   * - ``yam-real``
     - 3.11
     - YAM 控制和推理依赖。
   * - ``molmo-server``
     - 3.11
     - 独立的 Molmo 服务环境（``core = false``）。
   * - ``geometry-eval``
     - 3.11
     - 几何工具包及其冻结的 CPU 评测语料。
   * - ``sam3-server`` / ``openpi-server``
     - 3.11
     - 单能力诊断环境。

安装命令
--------

每个配方对应下面一条安装命令。新检出的仓库需要按上文先加上 ``uv run
--no-project --python 3.11 --with packaging -- python -m rpent.cli.env`` 前缀。

.. code-block:: bash

   rpent-env install minimal --venv .venv-minimal
   rpent-env install dev --venv .venv-dev
   rpent-env install libero-sim --venv .venv-libero-sim
   rpent-env install libero-pro --venv .venv-libero-pro
   rpent-env install libero-plus --venv .venv-libero-plus
   rpent-env install libero-pro-flywheel --venv .venv-libero-pro-flywheel
   rpent-env install libero-pro-molmo --venv .venv-libero-pro-molmo
   rpent-env install libero-openpi-external --venv .venv-libero-openpi-external
   rpent-env install franka-real --venv .venv-franka-real
   rpent-env install dual-franka-real --venv .venv-dual-franka-real
   rpent-env install robocasa-sim --venv .venv-robocasa-sim
   rpent-env install robotwin-sim --venv .venv-robotwin-sim
   rpent-env install robodojo-sim --venv .venv-robodojo-sim
   rpent-env install yam-real --venv .venv-yam-real
   rpent-env install molmo-server --venv .venv-molmo-server
   rpent-env install geometry-eval --venv .venv-geometry-eval
   rpent-env install sam3-server --venv .venv-sam3-server
   rpent-env install openpi-server --venv .venv-openpi-server

诊断与复现
----------

.. code-block:: bash

   rpent-env doctor --venv .venv-libero-pro
   rpent-env inspect --venv .venv-libero-pro
   rpent-env lock --all
   rpent-env lock --all --check

``doctor`` 将安装指纹与配方清单比较，检查 Python 和平台，运行 ``uv pip check`` 与组件探针，并可用 ``--endpoint molmo=host:port`` 探测外部 endpoint。开发时也可以用 ``rpent-env install <组件>`` 单独安装一个组件；它的指纹记录 ``install_kind = "component"``、``reproducible = false`` 及安装时使用的解释器，``doctor`` 会用这个解释器重建诊断配方，而不是用当前运行检查的解释器。``inspect`` 打印指纹及其 hash。``lock`` 用 ``uv pip compile`` 生成 ``envs/locks/<配方>.lock``；``--check`` 重新编译，结果与仓库中的锁不同时失败——上游发布新版本也会触发，所以它是 release 前的检查，不是 nightly 门禁；``Release install check`` 工作流在手动触发时运行 ``rpent-env lock --all --check``，它约束的是发布，不是 PR。``install`` 和 ``check`` 在安装前验证代价更低的不变量：每条直接需求仍被锁覆盖，锁定的 pin 仍满足清单。Linux 锁默认以 ``manylinux_2_31`` 为基线（glibc 2.31，即 Ubuntu 20.04 或更新版本），因为当前 GPU wheel 不再为更早的基线发布。若组件需要更新的基线，配方可用 ``manylinux`` 提高它；例如 RoboDojo 为 Isaac Sim 5.1 的 wheel 使用 ``manylinux = "2_35"``。``lock --all`` 会报告在当前主机上无法解析的配方并继续处理其余配方；``robotwin-sim`` 锁需要在设置了 ``CUDA_HOME`` 的 Linux 主机上生成，因为 cuRobo 在解析期间构建元数据。重新生成锁时使用较新的 ``uv``：旧版本对相同输入可能解析出不同版本，结果会与仓库中的锁不一致。

运行产物会在 ``run.json`` 中记录当前配方、指纹 hash、源码 commit 和组件名。

兼容 extra
----------

``scripts/gen_extras.py`` 根据同一组清单和配方生成 ``pyproject.toml`` 中的 ``[project.optional-dependencies]`` 和 ``[tool.uv].conflicts``。它们让 ``pip install -e ".[libero-pro]"`` 在一个发布周期内继续可用；不要手工修改该区块。``scripts/gen_extras.py --check`` 在区块过期时失败。受支持的接口是配方，extra 只用于迁移。

平台准备、checkpoint 和资产见各仿真器或机器人页面。
