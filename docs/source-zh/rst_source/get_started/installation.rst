安装
====

RPent 安装的是具名环境配方，而不是一组 extra。每个配方选择组件及其放置方式，每个组件在 ``component.toml`` 中声明自己的依赖。``rpent-install`` 创建虚拟环境，严格按该配方的锁安装，对每个在本地安装的组件执行导入探针，并写入安装指纹。

环境要求
--------

- Linux ``x86_64`` 和 `uv <https://docs.astral.sh/uv/getting-started/installation/>`_。
- 配方指定的 Python minor 版本；本机没有时，``rpent-install`` 会让 uv 下载。
- 仿真器和真机配方需要与该配方的 PyTorch 构建兼容的 GPU 和驱动。

查看配方
--------

.. code-block:: bash

   rpent-install list

该命令先列出每个组件及其类型和放置方式，再列出每个配方及其 Python 版本和组件。

用户配方位于 ``installs/profiles/``。测试与开发配方（``dev``、``unit-cpu``、``tool-geometry``）位于 ``tests/profiles/``；两个目录作为同一个命名空间被发现，同名配方会被拒绝。配方名遵循 ``<kind>-<name>[_<variant>]``，``kind`` 取 ``sim``、``real``、``model``、``tool`` 或 ``robot``；名称照抄组件名并保留下划线，变体用于选定组件的一个可选组（``sim-libero_pro``）。``minimal``、``dev`` 和 ``unit-cpu`` 沿用历史名称。

``robot-`` 配方是复合环境：它装一个仿真器或真机，外加该目标使用的模型。配方之间互不引用，仓库没有具名的组合拆成独立的 ``sim-``、``real-``、``model-`` 或 ``tool-`` 环境，运行时用 endpoint 连接。

安装配方
--------

在源码检出中安装配方并激活其环境：

.. code-block:: bash

   rpent-install install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

不传 ``--venv`` 时，配方安装到源码目录下的 ``.venvs/<配方>``；``.venvs/`` 是被 git 忽略的安装产物，之后的 ``install`` 和 ``doctor`` 会复用同一个环境。用 ``--venv`` 可以把环境放到其他位置。每个配方需要自己的环境：不同配方锁定不同的仿真器、机器人和模型运行时，因此安装器会拒绝安装到其他配方已安装的环境中。``--force`` 允许写入一个没有指纹记录的非空环境。

新检出的仓库还没有 ``rpent-install`` 命令。可以先不安装 RPent，直接引导它：

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.install install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

``rpent-install`` 需要在源码检出中运行。发布到 PyPI 的 wheel 只包含核心 ``rpent`` 包；``robots/``、``components/`` 及其 ``component.toml``、``installs/profiles/`` 只随源码检出和 sdist 发布。非可编辑的 ``pip install rpent`` 只提供 CLI；运行具体的机器人、模型服务或工具包请使用源码检出，这样 ``rpent-install`` 才能找到配方。

所有配方都从锁安装。用户配方的锁在 ``installs/locks/<配方>.lock``，测试配方的锁在 ``tests/locks/<配方>.lock``；配方也可以显式指定锁路径。安装前，安装器会检查锁存在，且仍覆盖每条直接需求和组件 override。锁缺失或过期时会失败，并给出重新生成它的命令：``python -m tests.tooling.lock <配方>``。

``core = false`` 的配方（例如 ``model-molmo``）不安装可编辑的 RPent，只包含该服务自己的依赖；启动时按 :doc:`../guides/flash` 的说明把源码目录放进 ``PYTHONPATH``。放在 ``remote`` 的组件只装客户端部分；在服务所在主机上安装运行该服务的 ``model-*`` 配方，运行时传入它的 endpoint。重复执行 ``install`` 会复用环境并修复过期安装。

配方
----

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - 配方
     - Python
     - 内容
   * - ``minimal``
     - 3.11
     - 仅核心 RPent，用于验证不安装扩展时的 CLI 和机器人发现。
   * - ``dev``
     - 3.10
     - 本地开发和 CI 使用的测试依赖。
   * - ``unit-cpu``
     - 3.10
     - 仅 CPU 的单元测试：核心、测试工具、CPU 版 Torch 和 CPU 版 flywheel 依赖。
   * - ``sim-libero_standard``
     - 3.11
     - LIBERO 仿真及 RLinf 运行时，用于 adapter 开发、e2e 和数据采集。
   * - ``sim-libero_pro``
     - 3.11
     - LIBERO-PRO 仿真，范围与 ``sim-libero_standard`` 相同。
   * - ``sim-libero_plus``
     - 3.11
     - LIBERO-plus 仿真，范围与 ``sim-libero_standard`` 相同。
   * - ``sim-robocasa``
     - 3.10
     - RoboCasa 仿真，含 RLinf 的 RoboCasa365 和 RLDX 栈。
   * - ``sim-robotwin``
     - 3.11
     - RoboTwin 仿真，含 LingBot-VLA 和 cuRobo。
   * - ``sim-robodojo``
     - 3.11
     - RoboDojo 及其 RLinf fork、Isaac Sim，不含策略和分割模型。
   * - ``real-franka`` / ``real-dual_franka``
     - 3.11
     - Franka 真机及平台依赖，不含策略模型。
   * - ``real-yam``
     - 3.11
     - 双臂 YAM 控制依赖，不含策略模型。
   * - ``robot-libero_pro``
     - 3.11
     - LIBERO-PRO，含 Pi0.5、SAM 3.0 以及 LeRobot 轨迹导出和回放。
   * - ``robot-franka``
     - 3.11
     - 单臂 Franka，含 Pi0.5。
   * - ``robot-dual_franka``
     - 3.11
     - 双臂 Franka，含 Pi0.5 和 SAM 3.0。
   * - ``robot-yam``
     - 3.11
     - 双臂 YAM，含 Pi0.5。
   * - ``robot-robodojo``
     - 3.11
     - RoboDojo 及其 RLinf fork、Isaac Sim、Pi0.5 和 SAM 3.0。
   * - ``model-molmo``
     - 3.11
     - 独立的 Molmo 视觉定位服务（``core = false``）。
   * - ``model-openpi`` / ``model-sam3``
     - 3.11
     - 单能力诊断环境。
   * - ``tool-flywheel``
     - 3.11
     - 不含仿真器和策略的 LeRobot 轨迹导出与回放。
   * - ``tool-geometry``
     - 3.11
     - 几何工具包及其冻结的 CPU 评测语料。

安装命令
--------

每个配方按其默认环境安装到 ``.venvs/<配方>``。新检出的仓库需要按上文先加上引导前缀。

.. code-block:: bash

   rpent-install install minimal
   rpent-install install dev
   rpent-install install unit-cpu
   rpent-install install sim-libero_standard
   rpent-install install sim-libero_pro
   rpent-install install sim-libero_plus
   rpent-install install sim-robocasa
   rpent-install install sim-robotwin
   rpent-install install sim-robodojo
   rpent-install install real-franka
   rpent-install install real-dual_franka
   rpent-install install real-yam
   rpent-install install robot-libero_pro
   rpent-install install robot-franka
   rpent-install install robot-dual_franka
   rpent-install install robot-yam
   rpent-install install robot-robodojo
   rpent-install install model-molmo
   rpent-install install model-openpi
   rpent-install install model-sam3
   rpent-install install tool-flywheel
   rpent-install install tool-geometry

诊断
----

.. code-block:: bash

   rpent-install doctor
   rpent-install doctor --venv .venvs/robot-libero_pro

不传 ``--venv`` 时，``doctor`` 检查当前激活的虚拟环境。``--profile`` 可以覆盖指纹中记录的配方。``doctor`` 将安装指纹与每项记录在案的安装输入比较（清单、安装时读取的锁、组件 override 文件，以及仓库的 ``[tool.uv]`` 设置），检查 Python 和平台，运行 ``uv pip check`` 与组件探针，并打印指纹路径及其 SHA-256。``remote`` 组件用 ``--endpoint <名称>=host:port`` 或 ``RPENT_<NAME>_ENDPOINT`` 探测；没有提供 endpoint 的 remote 组件报告为警告。``uv`` 的解析在源码检出中进行，所以比较的设置不随命令的执行目录变化；用户级 ``uv`` 配置（``~/.config/uv``）不在比较范围内。指纹还记录写入时使用的输入模式，由旧版 ``rpent-install`` 安装的环境会报告为需要重装，而不是环境已漂移。

运行产物会在 ``run.json`` 中记录当前配方、指纹 hash、源码 commit 和组件名。

维护者检查与锁
--------------

仓库结构检查和锁生成是 ``tests/tooling/`` 下的维护者工具，不随 wheel 安装，也不属于 ``rpent-install``。请在源码检出中运行：

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.check --all
   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.lock sim-robotwin
   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.lock --all --check

``check`` 读取清单和配方，计算每个配方的 ``requires`` 闭包，报告放置方式冲突、重复锁定、不支持的 Python 版本、平台不匹配，以及不再覆盖当前依赖的锁。它不会下载任何依赖。加上 ``--resolve`` 后，它还会用 ``uv pip compile`` 编译每个配方，确认声明的依赖可解；这与 ``lock`` 走同一条代码路径，会从配置的索引读取包元数据。

``lock`` 用 ``uv pip compile`` 生成每个配方的锁，并在首行记录上游截止时间 ``# exclude_newer``。``--check`` 按这个记录的截止时间重新编译，结果与仓库中的锁不同时失败，因此它反映的是清单变化或解析器版本不同，而不是期间的 upstream 发布。``lock --all`` 会报告在当前主机上无法解析的配方并继续处理其余配方；``sim-robotwin`` 的锁需要在设置了 ``CUDA_HOME`` 的 Linux 主机上生成，因为 cuRobo 在解析期间构建元数据。Linux 锁默认以 ``manylinux_2_31`` 为基线（glibc 2.31，即 Ubuntu 20.04 或更新版本），因为当前 GPU wheel 不再为更早的基线发布。若组件需要更新的基线，配方可用 ``manylinux`` 提高它；例如 ``robot-robodojo`` 为 Isaac Sim 5.1 的 wheel 使用 ``manylinux = "2_35"``。重新生成锁时使用生成当前锁的 ``uv`` 版本（0.13.7）：旧版本对相同输入可能解析出不同版本。发布任务固定使用该版本；升级它时要在同一次 relock 改动里一起修改。

其他维护者工具负责仓库结构和 CI 选择：``python -m tests.tooling.layout`` 检查组件边界，``python -m tests.tooling.extras --check`` 检查生成的 extra，``python -m tests.tooling.matrix`` 和 ``python -m tests.tooling.affected`` 选择并划分测试环境。CI 用上面相同的 ``uv run`` 引导方式运行它们。

兼容 extra
----------

``python -m tests.tooling.extras`` 根据同一组清单和配方生成 ``pyproject.toml`` 中的 ``[tool.rpent.extras]`` 和 ``[tool.uv].conflicts``。源码安装和可编辑安装由 ``setup.py`` 把 extras 表传给 ``extras_require``，因此 ``pip install -e ".[libero-pro]"`` 在一个发布周期内继续可用；发布的核心 wheel 不带 extras。不要手工修改生成的区块；区块过期时 ``--check`` 会失败。受支持的接口是配方，extra 只用于迁移。

平台准备、checkpoint 和资产见各仿真器或机器人页面。
