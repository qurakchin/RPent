安装
====

RPent 安装的是组件。每个组件在 ``component.toml`` 中声明自己的依赖、Python 支持范围和可用主机。``rpent-install install`` 创建虚拟环境，按这些清单解析出的依赖安装，对每个已安装的组件执行导入探针，并写入安装指纹。

环境是一个装有一组组件、名为所请求组件名排序后以 ``+`` 连接的虚拟环境，例如 ``infra-dev+robot-libero``；不指定组件时 ``install`` 创建只含核心的 ``minimal`` 环境。组件的 ``requires`` 指明它运行所需的组件，因此安装机器人时会一并安装它的仿真器、模型和工具。

环境要求
--------

- Linux ``x86_64`` 和 `uv <https://docs.astral.sh/uv/getting-started/installation/>`_。
  仿真器、模型和机器人运行时面向 Linux；安装器会记录解析所用的主机，开发环境也可以装在
  ``darwin-arm64`` 上。``check --platform`` 可以在不安装的情况下按其他主机解析。
- 受支持的 Python minor 之一：3.12、3.11 或 3.10。组件声明各自接受的范围；环境解析到满足
  闭包内所有组件的最新受支持 minor，本机没有时 ``rpent-install`` 会让 uv 下载。
- 仿真器和机器人环境需要与其 PyTorch 构建兼容的 GPU 和驱动。

查看组件
--------

.. code-block:: bash

   rpent-install list

该命令打印每个组件的名字、类型、它自己那个环境解析出的 Python minor 以及说明。

组件命名为 ``<kind>-<目录名>``：``robot``、``sim``、``model``、``tool`` 或 ``infra``。每个组件都可以按自己的名字安装成一个环境。``rpent-install install model-sam3`` 安装 SAM 3.0 服务，``rpent-install install sim-libero`` 只安装 LIBERO 仿真器而不带机器人适配层，``rpent-install install robot-libero`` 则把 LIBERO 连同其 ``requires`` 指明的仿真器、模型和工具一起装进同一个环境。

组件的 ``python`` 可以写版本（``"3.11"``），也可以写范围（``">=3.10,<3.13"``）。``install`` 从清单解析它；当清单现在解析出的输入与指纹记录不同时，``doctor`` 会报告出来。主机同样是安装输入：``install`` 记录解析所用的主机，``doctor`` 把它与环境运行的主机作比较。

安装环境
--------

在源码检出中安装组件环境并激活：

.. code-block:: bash

   rpent-install install robot-libero
   source .venvs/robot-libero/bin/activate

不传 ``--venv`` 时，环境安装到源码目录下的 ``.venvs/<环境名>``；``.venvs/`` 是被 git 忽略的安装产物，之后的 ``install`` 和 ``doctor`` 会找到同一个环境。用 ``--venv`` 可以把环境放到其他位置。每个环境需要自己的虚拟环境：不同环境锁定不同的仿真器、机器人和模型运行时，因此安装器会拒绝安装到其他环境已安装的虚拟环境中。``--force`` 允许写入一个有内容、属于其他工具的虚拟环境。``--dry-run`` 执行同样的解析校验，只打印该环境将要安装的依赖，不创建也不修改虚拟环境。

新检出的仓库还没有 ``rpent-install`` 命令。``./rpent-install.sh`` 负责引导，并把参数原样转给安装器，因此不需要事先准备任何环境：

.. code-block:: bash

   ./rpent-install.sh install robot-libero
   source .venvs/robot-libero/bin/activate

该脚本在一个一次性的 ``uv`` 环境里运行安装器，只额外加入 ``packaging``；本机只需要 ``uv`` 在 ``PATH`` 上。

``rpent-install`` 需要在源码检出中运行。发布到 PyPI 的 wheel 只包含核心 ``rpent`` 包；``robots/``、``components/`` 及其 ``component.toml`` 清单只随源码检出和 sdist 发布。非可编辑的 ``pip install rpent`` 只提供 CLI；运行具体的机器人或模型服务请使用源码检出，这样 ``rpent-install`` 才能找到清单。

``install`` 从清单解析环境，不读取锁：改动清单就会改变下一次安装创建的环境。``tests/locks/<环境名>.lock`` 下检入的锁是可选的复现产物，用于按维护者验证过的确切版本重建环境；它们不是安装输入，没有锁时 ``install`` 和 ``check`` 照常工作。用 ``python -m tests.tooling.lock <环境名>`` 重新生成锁。

每个环境都安装可编辑的源码检出，因此从某个环境启动的服务导入的正是安装它的那份检出。为其他环境提供服务的组件在服务所在主机上作为独立环境安装（``model-openpi`` 或 ``model-sam3``），调用方运行时传入它的 endpoint，用法见 :doc:`../guides/flash`。重复执行 ``install`` 会复用虚拟环境并修复过期安装。

自定义组合
----------

在命令行上指定多个组件即可组合成一个环境：

.. code-block:: bash

   rpent-install install robot-franka model-sam3
   source .venvs/model-sam3+robot-franka/bin/activate

环境以组件名排序后连接命名，因此命令行上的顺序无关紧要。指纹记录所请求的组件，``doctor`` 和 ``check`` 按同一组合重新解析，因此加进来的组件仍属于有记录的环境，不会脱离安装指纹。把环境名（包括 ``+`` 连接的组合）传给 ``check`` 即可在不安装的情况下解析它。

解析会按组件声明的索引检查整个闭包，所以 ``env_conflicts``、索引分歧、Python 范围冲突以及组件不支持的主机会在环境建好之前失败；``install --dry-run`` 只打印将要安装的依赖，不实际安装。

组件
----

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - 环境
     - Python
     - 内容
   * - ``minimal``
     - 3.12
     - 仅核心 RPent，用于验证不安装扩展时的 CLI 和机器人发现。
   * - ``infra-dev``
     - 3.12
     - 本地开发和 CI 使用的测试依赖。
   * - ``infra-unit_cpu``
     - 3.11
     - 仅 CPU 的单元测试：核心、``infra-dev`` 测试工具、CPU 版 Torch 和 CPU 版 flywheel 依赖。
   * - ``infra-rlinf``
     - 3.12
     - 仿真器和机器人环境共用的 RLinf 发布运行时。
   * - ``tool-flywheel``
     - 3.11
     - LeRobot 轨迹导出和回放。
   * - ``sim-libero``
     - 3.12
     - LIBERO 和 LIBERO-PRO 仿真，用于 adapter 开发、e2e 和数据采集。
   * - ``sim-libero_plus``
     - 3.12
     - LIBERO-plus 仿真任务，供 LIBERO adapter 使用。
   * - ``sim-robocasa``
     - 3.10
     - RoboCasa 仿真，含 RLinf 的 RoboCasa365 和 RLDX 栈。
   * - ``sim-robodojo``
     - 3.11
     - RoboDojo 仿真和 Isaac Sim，不带策略或分割模型。
   * - ``sim-robotwin``
     - 3.11
     - RoboTwin 仿真，含 cuRobo 和 RLinf 运行时。
   * - ``model-molmo``
     - 3.12
     - 独立环境中的 Molmo 视觉定位。
   * - ``model-openpi``
     - 3.12
     - Pi0.5 策略运行时。
   * - ``model-sam3``
     - 3.12
     - SAM 3.0 分割运行时。
   * - ``model-rldx``
     - 3.10
     - RoboCasa 使用的 RLDX 策略运行时。
   * - ``model-lingbot``
     - 3.11
     - RoboTwin 使用的 LingBot-VLA 策略运行时。
   * - ``model-awomo05``
     - 3.11
     - RoboDojo 使用的 Awomo05 原生关节策略。
   * - ``model-vpp2``
     - 3.11
     - RoboDojo 使用的 VPP2 视频预测策略。
   * - ``robot-libero``
     - 3.11
     - LIBERO，含 Pi0.5、SAM 3.0 以及 LeRobot 轨迹导出和回放。
   * - ``robot-franka``
     - 3.12
     - 单臂 Franka，含 Pi0.5 和 RLinf 运行时。
   * - ``robot-dual_franka``
     - 3.12
     - 双臂 Franka，含 Pi0.5 和 SAM 3.0。
   * - ``robot-yam``
     - 3.11
     - 双臂 YAM，含 Pi0.5 和 RLinf 运行时。
   * - ``robot-robodojo``
     - 3.11
     - RoboDojo 及其 RLinf fork、Isaac Sim、Pi0.5、SAM 3.0、Awomo05 和 VPP2。
   * - ``robot-robocasa``
     - 3.10
     - RoboCasa，含 RLinf 的 RoboCasa365 和 RLDX 栈。
   * - ``robot-robotwin``
     - 3.11
     - RoboTwin，含 LingBot-VLA 和 cuRobo。

其余组件（例如 ``model-apxinf``、``model-cosmos3`` 和 ``model-uniwam``）按自己的名字安装；``rpent-install list`` 会打印完整列表。机器人的行包含其 ``requires`` 指明的组件，所以安装它会创建一个含全部组件的环境。Python 列给出清单当前解析出的 minor，它可能比清单接受的范围更窄。

安装命令
--------

每个环境都安装到 ``.venvs/<环境名>`` 下的默认虚拟环境。新检出的仓库需要按上文先加上引导前缀。

.. code-block:: bash

   rpent-install install
   rpent-install install infra-dev
   rpent-install install infra-unit_cpu
   rpent-install install sim-libero
   rpent-install install sim-libero_plus
   rpent-install install sim-robocasa
   rpent-install install sim-robodojo
   rpent-install install sim-robotwin
   rpent-install install robot-libero
   rpent-install install robot-franka
   rpent-install install robot-dual_franka
   rpent-install install robot-yam
   rpent-install install robot-robodojo
   rpent-install install robot-robocasa
   rpent-install install robot-robotwin
   rpent-install install model-molmo
   rpent-install install model-openpi
   rpent-install install model-sam3

诊断
----

.. code-block:: bash

   rpent-install doctor
   rpent-install doctor --venv .venvs/robot-libero

不传 ``--venv`` 时，``doctor`` 检查 shell 中激活的虚拟环境，找不到时退回运行 ``rpent-install`` 的那个环境；输出的第一行会写明实际检查的环境。``doctor`` 将安装指纹与各项安装输入比较（清单、组件 override 文件，以及仓库的 ``[tool.uv]`` 设置），检查 Python 和平台，运行 ``uv pip check`` 与组件探针，并打印指纹路径及其 SHA-256。``doctor`` 还会用 ``--endpoint <名称>=host:port`` 或 ``RPENT_<NAME>_ENDPOINT`` 探测装在另一个环境中的服务，并报告连不上的 endpoint。``uv`` 的解析在源码检出中进行，所以比较的设置不随命令的执行目录变化；用户级 ``uv`` 配置（``~/.config/uv``）不在比较范围内。指纹还记录写入时使用的输入模式，由旧版 ``rpent-install`` 安装的环境会报告为需要重装，而不是环境已漂移。

运行产物会在 ``run.json`` 中记录环境名与指纹 hash；指纹本身仍保存在对应环境中。

维护者检查与复现锁
------------------

``rpent-install check`` 从清单解析环境而不安装任何东西：

.. code-block:: bash

   rpent-install check --all
   rpent-install check minimal --inputs-hash
   rpent-install check robot-robotwin --resolve --platform linux-x86_64

它计算每个环境的 ``requires`` 闭包，报告依赖冲突、未知或互斥的组件、不支持的 Python 版本以及平台不匹配。它不会下载任何依赖，也不需要锁。每个位置参数都是一个环境名，可以是 ``+`` 连接的组合；不传时检查 ``minimal``。``--inputs-hash`` 打印单个环境安装输入的 hash 及其解析出的 Python minor；CI 用它作为环境缓存键。加上 ``--resolve`` 后，它还会用 ``uv pip compile`` 编译所选环境，确认声明的依赖可解；这与 ``lock`` 走同一条代码路径，会从配置的索引读取包元数据。``--platform`` 指定解析所用的主机，默认 ``linux-x86_64``。

``tests/tooling/`` 下的其余维护者工具不随 wheel 安装。请在源码检出中通过 ``tests/tooling/run.sh`` 运行，它把模块名和参数转给一次性的 ``uv`` 环境：

.. code-block:: bash

   tests/tooling/run.sh rpent.cli.install check --all
   tests/tooling/run.sh tests.tooling.lock sim-robotwin
   tests/tooling/run.sh tests.tooling.lock --all --check

``lock`` 用 ``uv pip compile`` 生成环境的复现锁，并在首行记录上游截止时间 ``# exclude_newer``。锁位于 ``tests/locks/<环境名>.lock``，不改变 ``install`` 的行为。``--check`` 按这个记录的截止时间重新编译，结果与仓库中的锁不同时失败，因此它反映的是清单变化或解析器版本不同，而不是期间的 upstream 发布。``lock --all`` 会报告在当前主机上无法解析的环境并继续处理其余环境；``sim-robotwin`` 的锁需要在设置了 ``CUDA_HOME`` 的 Linux 主机上生成，因为 cuRobo 在解析期间构建元数据。Linux 锁默认以 ``manylinux_2_31`` 为基线（glibc 2.31，即 Ubuntu 20.04 或更新版本），因为当前 GPU wheel 不再为更早的基线发布。闭包采用其中组件声明的最高基线；例如 ``sim-robodojo`` 为 Isaac Sim 5.1 的 wheel 声明 ``manylinux = "2_35"``。重新生成锁时使用生成当前锁的 ``uv`` 版本（0.13.7）：旧版本对相同输入可能解析出不同版本；升级它时要在同一次 relock 改动里一起修改。

其他维护者工具负责仓库结构和 CI 选择：``python -m tests.tooling.layout`` 检查组件边界，``python -m tests.tooling.matrix`` 和 ``python -m tests.tooling.affected`` 选择并划分测试环境。CI 用上面相同的 ``uv run`` 引导方式运行它们。

平台准备、checkpoint 和资产见各仿真器或机器人页面。
