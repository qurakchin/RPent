RoboDojo 后端环境安装与复现
============================

本页是 RoboDojo 后端安装的概要。命令完整、可照抄的权威指南（三运行时
布局、editable IsaacLab、CuRobo、JAX→PyTorch checkpoint 转换、norm stats
以及全部必需环境变量）见 ``docs/ROBODOJO_INSTALLATION.md``。

以下概要在 Linux x86_64 工作站（NVIDIA RTX PRO 6000 Blackwell、驱动
580.173.02、Ubuntu 24.04）上端到端验证通过；权威指南中的观测另行在一台
RTX 4090（驱动 550.127.08）上复现。

运行时构成
----------

集成刻意保持三个隔离的运行时，外加大型资产与一个 planner 凭证；RPent
只负责编排，绝不混用：

.. list-table::
   :header-rows: 1

   * - 运行时
     - Python
     - 内容
     - 用途
   * - RPent venv
     - 3.11
     - rpent 本体 + SAM3
     - agent 循环 / 工具 / 记忆
   * - robodojo-sim
     - 3.11
     - Isaac Sim 5.1 / IsaacLab 0.54.3 / CuRobo（或 import stub）
     - 仿真环境
   * - Pi0.5 策略环境（uv）
     - 3.11
     - RLinf + rpent-openpi（openpi Pi0.5）
     - 策略服务

前置条件
--------

* Linux x86_64，NVIDIA GPU，约 100–180 GB 磁盘；
* RoboDojo 官方 checkpoint（RoboDojo-sim-arx_x5-joint-0，发布约 44.7 GB，
  本次复现未完整下载）与 ``Assets/`` 树（实测 15,365 文件 / 41.27 GB，
  39 GiB），来自 ModelScope；
* SAM3 checkpoint（约 3.45 GB）与 CLIP BPE 词表（已随 sam3 wheel 打包）；
* 驱动：上游要求 570.x 及以上（CUDA 12.8）；实测驱动 550 可经 CUDA 12.x
  次版本兼容运行。

RPent + SAM3
------------

.. code-block:: bash

   # 从 rpent checkout 的父目录安装，避免只面向 sim 环境的
   # [tool.uv] override-dependencies 作用到 agent 依赖栈。
   uv pip install -e "./rpent[robodojo]"   # RoboDojo 完整安装

``.[robodojo]`` 是唯一正确的 RoboDojo extra：它拉入 ``robodojo-sim``、
``sam3`` 以及固定版本的 ``rlinf`` / ``rpent-openpi`` git 依赖。不存在
``openpi`` extra；单独 ``.[sam3]`` 缺 Isaac Sim / IsaacLab / CuRobo。
Blackwell 上请固定 ``torch==2.7.1+cu128`` / ``torchvision==0.22.1+cu128``。

RoboDojo 源码
-------------

克隆 RoboDojo 官方仓库（含 XPolicyLab 子模块），并固定到与本地验证一致的
pinned 提交。RPent runner 读取工作区文件
``<ROBODOJO_WORKSPACE>/config/runtime.env``，其键为
``ROBODOJO_SOURCE_ROOT``、``ROBODOJO_XPOLICYLAB_ROOT``、
``ROBODOJO_SIM_ENV``、``ROBODOJO_PI05_ENV``。

仿真环境（Isaac Sim / IsaacLab / CuRobo）
------------------------------------------

* ``isaacsim[all,extscache]==5.1.0``；
* 使用 pinned IsaacLab 0.54.3 fork。IsaacLab **必须 editable 安装**
  （``-e source/isaaclab`` 加 ``_assets``、``_tasks``）：非 editable 的
  VCS 子目录安装只带 ``__init__.py``，会丢 ``config/extension.toml``。
  ``robodojo-sim`` extra 里的 git 引用只是为了让 extra 可解析，并不是可用
  的 IsaacLab 安装方式；
* ``h5py`` 必须补进 sim 环境（``isaaclab_tasks`` 会 import 它）；
* CuRobo 由 ``env/robot_manager/robot_manager.py`` ->
  ``env/planner_manager/curobo_planner`` 在模块级 import。pinned fork 是 v2
  重写，通过 ``cuda.core`` 在运行时 JIT 编译 kernel，因此
  ``nvidia-curobo[cu12]`` 是普通 Python 安装（安装期不编译 CUDA），kernel
  在首次构造 planner 时编译。需要 IK / ee 动作时把它 editable 装进 sim
  环境；没有 CuRobo 的机器可用 import-only stub 加条件化
  ``need_planner: False``。注意：装了真 CuRobo 后 stub 绝不能留在
  ``PYTHONPATH`` 上，因为 ``PYTHONPATH`` 先于 ``site-packages``，会遮蔽真包；
* 克隆资产后**必须**执行：在 RoboDojo 仓库根目录运行
  ``python utils/update_embodiment_config_path.py`` 生成真正的 planner 配置。
  它会写出 ``Assets/Robots/<robot>/curobo.yml`` 并把**绝对**资产路径烘进去，
  因此仓库/资产位置一变就必须重跑。缺了它 ``CuroboPlanner`` 会以
  ``FileNotFoundError: .../Assets/Robots/x5/curobo.yml`` 失败。生成后 env
  server 日志出现 ``CuRobo planner AVAILABLE``，``env.get_status`` 报
  ``ik_available: true``。

RoboDojo 资产
-------------

实测 ``Assets/`` 树为 15,365 文件 / 41.27 GB（39 GiB）。此处原先引用的
``14,506`` 个 LFS 文件与 ``9,224`` 个 eval layout 数字无法针对固定
checkout 核实，请按"未验证"对待。

Pi0.5 策略环境
--------------

单独建一个含 RLinf 与 ``rpent-openpi``（openpi Pi0.5）的环境，然后把发布
的 JAX/orbax checkpoint 转成 PyTorch，因为 loader 只接受
``*.safetensors`` 或 ``model_state_dict/full_weights.pt``：

.. code-block:: bash

   ln -sfn <ckpt>/59999 ckpt_torch/jax_pi05_src
   venv_policy/bin/python -m rlinf.utils.ckpt_convertor.convert_openpi_jax_to_python \
     --checkpoint-dir "$PWD/ckpt_torch/jax_pi05_src" \
     --output-path  "$PWD/ckpt_torch/pi05_robodojo_arx_x5" \
     --config-name pi05_aloha --precision bfloat16

必须以模块方式运行（用脚本路径运行会让
``rlinf/utils/ckpt_convertor/openpi/`` 遮蔽真正的 ``openpi`` 包），且
``--checkpoint-dir`` 必须包含小写 ``pi05``（转换器按该子串分支）。

接线与冒烟
----------

``robots/robodojo/robot_spec.py`` 读取
``<ROBODOJO_WORKSPACE>/config/runtime.env``（``ROBODOJO_SIM_ENV``、
``ROBODOJO_PI05_ENV``、``ROBODOJO_SOURCE_ROOT``、
``ROBODOJO_XPOLICYLAB_ROOT``）；需设置 ``ROBODOJO_WORKSPACE`` 让 CLI 找到
它。必需环境变量：``PI05_CHECKPOINT_PATH``、``PI05_NORM_STATS_PATH``
（**含** ``norm_stats.json`` 的目录）、``SAM3_CHECKPOINT_PATH`` 以及 LLM
凭证（``claude_code`` 精确检查 ``ANTHROPIC_API_KEY``）。冒烟链路：

.. code-block:: text

   robodojo.sh doctor（RoboDojo 工作区） -> 官方 Pi0.5 debug gate ->
   裸 eval -> rpent --robot robodojo ...

三服务全量运行的实测峰值显存为 20,242 MiB（24 GB 卡；env 约 6.6 GB、
Pi0.5 约 7.9 GB、SAM3 约 4 GB）。原先的 ``~45 GB`` 数字来自另一台主机，
不应再用于容量规划。完整命令序列、排障表与已知 pin 见
``docs/ROBODOJO_INSTALLATION.md`` 与 ``robots/robodojo/guides/interface.md``。

.. note::

   ``.[robodojo]`` 只安装 Python 包。之后 IsaacLab **必须 editable 安装**
   （非 editable 的 VCS 子目录安装会丢 ``config/extension.toml``）；上游
   import 链要求 CuRobo（或用 import-only stub 加 ``need_planner: False``）；
   发布的 JAX/orbax checkpoint 必须先转成 PyTorch 策略才能加载。命令完整的
   指南见 ``docs/ROBODOJO_INSTALLATION.md``。

