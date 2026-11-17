安装
====

RPent 安装的是具名环境配方，而不是一组 extra。``installs/profiles/`` 中的每个配方选择组件及其放置方式，每个组件在 ``component.toml`` 中声明自己的依赖。``rpent-install`` 创建虚拟环境，只安装该配方的内容，对每个在本地安装的组件执行导入探针，并写入安装指纹。

环境要求
--------

- Linux ``x86_64`` 和 `uv <https://docs.astral.sh/uv/getting-started/installation/>`_。
- 配方指定的 Python minor 版本；本机没有时，``rpent-install`` 会让 uv 下载。
- 仿真器和真机配方需要与该配方的 PyTorch 构建兼容的 GPU 和驱动。

查看与检查配方
--------------

.. code-block:: bash

   rpent-install list
   rpent-install check --all

``check`` 读取清单和配方，计算 ``requires`` 闭包，报告放置方式冲突、重复的版本固定、不支持的 Python 版本和平台不匹配。它不会下载任何依赖。加上 ``--resolve`` 后，它还会用 ``uv pip compile`` 检查声明的依赖是否可解；这会从配置的索引读取包元数据，检查后删除临时生成的 requirements。

安装配方
--------

在源码目录中把配方安装到独立的虚拟环境：

.. code-block:: bash

   rpent-install install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

新检出的仓库还没有 ``rpent-install`` 命令。可以先不安装 RPent，直接引导它：

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.install install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

``rpent-install`` 需要在源码检出中运行。发布到 PyPI 的 wheel 只包含核心 ``rpent`` 包；``robots/``、``components/`` 及其 ``component.toml``、``installs/profiles/`` 只随源码检出和 sdist 发布。非可编辑的 ``pip install rpent`` 只提供 CLI；运行具体的机器人、模型服务或工具包请使用源码检出（或 sdist），在 pip 安装的环境里 ``rpent-install`` 会报告找不到配方。

每个配方使用自己的虚拟环境。不同配方对仿真器、机器人和模型运行时有不同的依赖约束，安装器会拒绝在已安装其他配方的环境中安装；请为它指定另一个 ``--venv``。不传 ``--venv`` 时，配方安装到源码目录下的 ``.rpent/venvs/<配方>``；``.rpent/`` 是本地状态、已被 git 忽略，之后的 ``install`` 和 ``doctor`` 会复用同一个环境。``core = false`` 的配方（例如 ``molmo-server``）不安装可编辑的 RPent，只包含该服务自己的依赖；启动时按 :doc:`../guides/flash` 的说明把源码目录放进 ``PYTHONPATH``。

重复执行会复用环境并修复过期安装。安装器根据配方和组件清单生成 requirements，再由 ``uv pip install`` 解析安装。清单中的直接依赖版本约束和 Git revision 仍然生效；随着上游发布新版本，不同时间全新安装的传递依赖版本可能不同。``--dev`` 将测试依赖追加到生成的 requirements，``--dry-run`` 只打印这些 requirements。配方把组件放到外部环境时，安装器会打印该环境的安装命令；请在同一个源码目录中执行。

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
     - 测试和 lint 依赖；可用 ``rpent-install install <配方> --dev`` 附加到其他配方。
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
   * - ``sam3-server`` / ``openpi-server``
     - 3.11
     - 单能力诊断环境。

安装命令
--------

每个配方对应下面一条安装命令。新检出的仓库需要按上文先加上 ``uv run
--no-project --python 3.11 --with packaging -- python -m rpent.cli.install`` 前缀。

.. code-block:: bash

   rpent-install install minimal --venv .venv-minimal
   rpent-install install dev --venv .venv-dev
   rpent-install install libero-sim --venv .venv-libero-sim
   rpent-install install libero-pro --venv .venv-libero-pro
   rpent-install install libero-plus --venv .venv-libero-plus
   rpent-install install libero-pro-flywheel --venv .venv-libero-pro-flywheel
   rpent-install install libero-pro-molmo --venv .venv-libero-pro-molmo
   rpent-install install libero-openpi-external --venv .venv-libero-openpi-external
   rpent-install install franka-real --venv .venv-franka-real
   rpent-install install dual-franka-real --venv .venv-dual-franka-real
   rpent-install install robocasa-sim --venv .venv-robocasa-sim
   rpent-install install robotwin-sim --venv .venv-robotwin-sim
   rpent-install install robodojo-sim --venv .venv-robodojo-sim
   rpent-install install yam-real --venv .venv-yam-real
   rpent-install install molmo-server --venv .venv-molmo-server
   rpent-install install sam3-server --venv .venv-sam3-server
   rpent-install install openpi-server --venv .venv-openpi-server

环境诊断
--------

.. code-block:: bash

   rpent-install doctor --venv .venv-libero-pro
   rpent-install inspect --venv .venv-libero-pro

``doctor`` 将安装指纹与每项记录在案的安装输入比较（清单、组件 override 文件，以及仓库的 ``[tool.uv]`` 设置），检查 Python 和平台，运行 ``uv pip check`` 与组件探针，并可用 ``--endpoint molmo=host:port`` 探测外部 endpoint。``uv`` 的解析在仓库根目录进行，所以比较的设置不随命令的执行目录变化；用户级 ``uv`` 配置（``~/.config/uv``）不在比较范围内；指纹还记录写入时使用的输入模式，由旧版 ``rpent-install`` 安装的 venv 会报告为需要重装，而不是环境已漂移。开发时也可以用 ``rpent-install install <组件>`` 单独安装一个组件；它的指纹记录 ``install_kind = "component"`` 及安装时使用的解释器，``doctor`` 会用这个解释器重建诊断配方，而不是用当前运行检查的解释器。``inspect`` 打印指纹及其 hash。``doctor`` 还会比较当前安装包集合与记录的 freeze hash。这些检查用于发现环境变化，不会固定将来解析出的依赖版本。发布工作流以 ``full: true`` 调用 Full CI，在发布前安装并诊断每个配方。

执行 ``check --resolve`` 时，Linux 配方默认以 ``manylinux_2_31`` 为基线（glibc 2.31，即 Ubuntu 20.04 或更新版本）。配方可用 ``manylinux`` 提高基线；例如 RoboDojo 为 Isaac Sim 5.1 的 wheel 使用 ``manylinux = "2_35"``。对 ``robotwin-sim`` 使用 ``--resolve`` 需要设置了 ``CUDA_HOME`` 的 Linux 主机，因为 cuRobo 在解析期间构建元数据。某个配方解析失败时会报告错误并继续检查其余配方。

运行产物会在 ``run.json`` 中记录当前配方、指纹 hash、源码 commit 和组件名。

兼容 extra
----------

``rpent-install extras`` 根据同一组清单和配方生成 ``pyproject.toml`` 中的 ``[project.optional-dependencies]`` 和 ``[tool.uv].conflicts``。它们让 ``pip install -e ".[libero-pro]"`` 在一个发布周期内继续可用；不要手工修改该区块。``rpent-install extras --check`` 在区块过期时失败。受支持的接口是配方，extra 只用于迁移。

平台准备、checkpoint 和资产见各仿真器或机器人页面。
