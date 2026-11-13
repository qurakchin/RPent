RoboDojo
========

通过 RPent 在 RoboDojo 中执行双臂桌面操作任务。仿真器基于 Isaac Sim / IsaacLab，采用 ARX-X5 双机械臂平台。RPent 结合策略动作、原生运动 Primitive 和 SAM3 物体分割完成任务。策略动作可选择 VPP2 或 Awomo05。

.. page-head::
   :for: 要在 RoboDojo 中用 Isaac Sim 运行 ARX-X5 双臂任务的读者
   :outcome: 安装 RoboDojo、选择 VPP2 或 Awomo05、运行任务，并检查结果
   :read-when: 需要 Isaac Sim、选择策略，或使用 RoboDojo 专属参数时
   :skip-when: 还没有安装 RPent；先完成 :doc:`../get_started/quickstart`

**本文结构：** 概览 → 安装 → VLA 配置 → SAM3 配置 → 运行一个任务 → 查看结果 → 任务 → 验证状态 → 任务记忆 → 探索模式 → 常用参数 → 规划器可调用的工具。

概览
----

.. grid:: 2 4 4 4
   :gutter: 2

   .. grid-item-card:: 动作模型

      解析式 Primitive 和 VPP2（默认）、Awomo05

   .. grid-item-card:: 规划器

      ``api``、``claude_code``、``codex``

   .. grid-item-card:: 任务

      瓶子入桶、笔筒整理、碗堆叠等桌面操作。

   .. grid-item-card:: 硬件

      Linux、NVIDIA GPU；Python 3.11；Isaac Sim 5.1。

安装
----

NVIDIA 驱动版本建议参考 `Isaac Sim 5.1 官方系统要求 <https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html>`_。\
宿主机还需具备构建 cuRobo 所需的 CUDA toolkit/NVCC 和编译工具链。先完成 :ref:`quickstart-install`，再在同一环境中安装仿真器依赖：

.. code-block:: bash

   uv pip install -e ".[robodojo-sim,sam3]" --extra-index-url https://pypi.nvidia.com \
     --override requirements/robodojo-override.txt

.. note::

   Blackwell GPU 需要 CUDA 12.8 版 PyTorch。本项目固定的 PyTorch 2.7.0 也提供 CUDA 12.6 构建，\
   但该构建不支持 Blackwell。使用这类 GPU 时，首次安装及后续重新安装都使用以下命令，\
   通过 ``--torch-backend=cu128`` 选择 CUDA 12.8 构建：

   .. code-block:: bash

      uv pip install -e ".[robodojo-sim,sam3]" --extra-index-url https://pypi.nvidia.com \
        --override requirements/robodojo-override.txt \
        --torch-backend=cu128

   如果环境中已安装 ``torch==2.7.0+cu126``，uv 会认为它满足版本要求，继续保留原有安装。\
   此时需在上面的命令末尾再添加 ``--reinstall-package torch --reinstall-package torchvision``，\
   强制替换为 CUDA 12.8 构建。

当前固定的 IsaacLab 版本需要 editable 安装，才能找到扩展配置。克隆到一个可写目录，并在同一环境中执行：

.. code-block:: bash

   git clone --no-checkout https://github.com/yuechen0614/IsaacLab.git /path/to/IsaacLab
   git -C /path/to/IsaacLab checkout afca7b09d60d8beb9c1cb28b43066499940b969b
   uv pip install --no-deps \
     -e /path/to/IsaacLab/source/isaaclab \
     -e /path/to/IsaacLab/source/isaaclab_assets \
     -e /path/to/IsaacLab/source/isaaclab_tasks

安装后保留该源码目录，运行时仍会使用它。

下载资源
~~~~~~~~

从 `RoboDojo 数据集 <https://huggingface.co/datasets/RoboDojo-Benchmark/RoboDojo>`_ 下载机器人、物体、材质和布局文件，\
并设置资源目录：

.. code-block:: bash

   hf download RoboDojo-Benchmark/RoboDojo --repo-type dataset \
     --include 'Assets/**' --local-dir /path/to/robodojo
   export ROBODOJO_ASSETS_ROOT=/path/to/robodojo

下载后，目录中应有 ``Assets/Robots``、``Assets/Object``、``Assets/Material`` 和 ``Assets/Eval_Layout``。

运行以下命令，将 ``Assets/Robots`` 下的 ``*_tmp.yml`` 模板生成为同目录下的 ``*.yml`` 配置，并填入本机资源的绝对路径。\
仿真器使用的 x5 配置为 ``Assets/Robots/x5/curobo.yml``：

.. code-block:: bash

   python - <<'PY'
   import os
   import runpy
   from robodojo_runtime import source_root

   script = source_root() / "utils/update_embodiment_config_path.py"
   os.chdir(os.environ["ROBODOJO_ASSETS_ROOT"])
   runpy.run_path(str(script), run_name="__main__")
   PY
   test -s "$ROBODOJO_ASSETS_ROOT/Assets/Robots/x5/curobo.yml"

首次下载后需要执行一次，之后运行任务时无需重复执行。若移动了资源目录，配置中保存的路径就会失效，需要重新运行此命令。\
重新生成会覆盖已有的 ``*.yml`` 配置。

场景引用的部分 NVIDIA 素材默认在线加载。离线运行或相关资源持续加载失败时，参见 :doc:`robodojo_reference` 中的 :ref:`robodojo-local-nvidia-assets`。

VLA 配置
--------

通过 ``--am-backend vpp2|awomo05`` 选择动作模型；省略时默认使用 ``vpp2``。模型实现与权重如下：

- VPP2：官方 `VPP2 RoboDojo 实现 <https://github.com/roboterax/video-prediction-policy-2/tree/72c17acf022494ff63617be86079bb92e92f5bf8>`_，以及 `Haodong082399/VPP2 <https://huggingface.co/Haodong082399/VPP2>`_ 发布的配对 100k 权重。
- Awomo05：`官方实现 <https://github.com/Awomo-WestlakeDI/Awomo-0.5>`_、`XPolicyLab RoboDojo 评测适配器 <https://github.com/XPolicyLab/XPolicyLab/blob/562c14cf08b9e6e411e7d76f192740afced77160/policy/Awomo05/README.md>`__，以及 `Auwomo/Awomo-0.5-Robodojo 权重与配套统计文件 <https://huggingface.co/Auwomo/Awomo-0.5-Robodojo>`_。

VPP2、Awomo05 的 worker 配置和离线 NVIDIA 素材见 :doc:`robodojo_reference`。



SAM3 配置
---------

SAM3 用于物体分割。下载块由 :ref:`quickstart-download` 维护；首次执行前，先在
`facebook/sam3 模型页面 <https://huggingface.co/facebook/sam3>`_ 申请访问权限：

.. include:: /_snippets/sam3-download.rst

运行一个任务
------------

先按 :doc:`../guides/configure_planner` 选择并配置要使用的 planner 和模型。以下以 Codex 为例，\
在运行任务的同一终端检查连接：

.. code-block:: bash

   rpent-check-llm --planner codex --model <planner-model> --json

将 ``<planner-model>`` 替换为所选模型名，配置好 VPP2 和 SAM3 后，在 seed 组 0、layout 0 上运行瓶子入桶任务：

.. code-block:: bash

   # 使用当前环境中安装的 RLinf 集成。
   export RPENT_RLINF_ROOT="$(python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"

   export ROBODOJO_PLACEMENT_SETTLE_STEPS=1000  # 推荐：让物体充分稳定；不设置时默认等待 20 步
   export OMNI_KIT_ACCEPT_EULA=YES  # 推荐用于首次非交互启动，提前接受 Kit 许可；已接受时可省略
   # Isaac Sim 启动需数十秒，首次运行还会编译 shader
   rpent --robot robodojo --am-backend vpp2 \
     --task put_bottles_into_dustbin --seed 0 --layout 0 \
     --planner codex --model <planner-model> --reasoning-effort medium \
     --max-turns 10000 --planner-timeout-s 1500 \
     --output-dir /path/to/run-output

查看结果
--------

终端会显示服务启动信息、planner 输出和工具调用。运行结束后，查看 ``--output-dir`` 指定目录中的文件：

- ``result.json``：环境的任务成功判定及运行错误状态。
- ``states.json``：工具命令、执行结果及同帧观测记录。
- 各相机逐步保存的 RGB、米制深度、标定和世界坐标三维图。
- ``videos/``：头部、左腕和右腕相机的视频。
- ``robodojo_env_server.log``、``sam3_server.log``、``robodojo_vpp2_server.log`` 或 ``robodojo_awomo05_server.log``：\
  本地启动服务的日志和报错信息。
- ``run.log`` 和 ``transcript_*.json``：主进程日志、planner 对话和错误。

先检查 ``environment_result_available=true`` 和\
``agent_error_present=false``，再看 ``success`` 是否为 ``true``。该字段记录 RoboDojo 的原生任务判定，\
``finish`` 用于结束规划循环。

未指定输出目录时，结果保存在 ``logs/<timestamp>_robodojo_<task>_s<seed>_l<layout>/``；使用 ``--random`` 时后缀为 ``<task>_random``，不包含 seed 和 layout。并发运行应使用不同目录。\
实时查看方式见 :doc:`../guides/dashboard`。

``score`` 记录原生任务进度分数，范围为 0–100。成功回合记为 100；失败回合
使用原生阶段分数，没有阶段评分的任务记为 0。运行器在工具执行结束后、
环境关闭前采集分数，不将其加入规划器反馈。``score_available=false`` 且
``score=null`` 表示未取得分数；读取失败时还会记录 ``score_error``。
``eval-fair`` 模式禁止访问评测结果，因此不提供 Score。

任务
----

`RoboDojo 仿真任务目录 <https://robodojo-benchmark.com/doc/sim-tasks/>`_ 将 42 个基准任务分为五类能力：

.. list-table::
   :header-rows: 1

   * - 类别
     - 任务数
     - 考察内容
   * - 泛化
     - 12
     - 不同物体和布局，包括随机变体。
   * - 记忆
     - 6
     - 状态追踪和顺序记忆。
   * - 精细操作
     - 8
     - 空间约束严格的操作。
   * - 长程任务
     - 8
     - 需要完成多个子目标的多步骤任务。
   * - 开放任务
     - 8
     - 开放式或依赖语言、图像指令的任务。

观测与动作
~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 项目
     - 说明
   * - 观测
     - 头部和左右腕部相机的 RGB-D 图像、相机标定，以及双臂关节状态、末端执行器位姿和夹爪开合状态。
   * - 动作
     - ``move_to``、``rotate_wrist``、``set_gripper``、``release`` 和 ``vpp2_act``、``awomo05_act``。``finish`` 不能覆盖原生任务判定。
   * - 奖励与成功判定
     - 任务是否成功由 RoboDojo 原生环境判定，结果记录在 ``result.json`` 的 ``success`` 字段中。
   * - 任务指令
     - 来自当前场景的 RoboDojo 任务描述，通过 ``view_env_state`` 读取。

验证状态
--------

- 已验证（单次）：v0.1 发布说明检查了安装与 ``put_bottles_into_dustbin`` 的一次执行。这验证安装与执行流程，不是任务成功率评测；见 :doc:`发布说明 <../resources/release_v0.1>`。
- 仅 CPU：离线单测覆盖配置、工具与结果契约。

任务记忆
--------

使用记忆见 :doc:`../guides/memory`。

评测时，规划器只读取记忆库中的内容，不对其进行修改。规划器参考同一任务版本在 seed 0、layout 0 上生成的任务记录和动作序列。记录为 JSON，动作序列为 JSONL。对应的 task-family 经验和相关 global 经验也作为参考。普通版与 ``*_random`` 版本的参考文件分开使用；缺少参考时，规划器记录缺失并根据当前观测继续。其他探索场景的产物可以作为经验保留，但不是评测 prompt 的默认参考。

使用已准备的本地记忆进行评测：

.. code-block:: bash

   rpent --robot robodojo --am-backend vpp2 \
     --task stack_blocks --seed 1 --layout 0 \
     --planner codex --model <planner-model> --reasoning-effort low \
     --memory-profile local --memory-dir /path/to/robodojo-memory \
     --max-turns 10000 --max-episode-steps 10000 --planner-timeout-s 4800 \
     --output-dir /path/to/eval-output

使用已发布的 Hugging Face 记忆时，将本地记忆参数替换为 ``--memory-profile hf`` 和 ``--memory-repo RLinf/RPent-memory@COMMIT_SHA``。RPent 从指定数据集版本的 ``robodojo/`` 目录读取记忆；将 ``COMMIT_SHA`` 替换为要使用的数据集提交 SHA。来源选择和发布流程见 :doc:`../guides/memory`。

探索模式
--------

探索模式在同一任务、seed 组和 layout 上反复尝试。默认最多运行 3 个规划会话，每个会话最多尝试 5 次。工作笔记和待整理的经验保存在本地。环境判定任务成功后，不再启动后续会话。按前文配置服务后，执行：

.. code-block:: bash

   rpent --robot robodojo --am-backend vpp2 \
     --task stack_blocks --seed 0 --layout 0 --explore \
     --planner codex --model <planner-model> --reasoning-effort low \
     --memory-dir /path/to/robodojo-memory \
     --explore-sessions 3 --explore-attempts-per-session 5 \
     --max-turns 10000 --max-episode-steps 10000 --planner-timeout-s 4800 \
     --output-dir /path/to/explore-output

使用 ``--task stack_blocks_random`` 探索保存好的随机化版本。``--random`` 参数会生成新场景，因此探索模式不支持它。两个示例中的 ``--max-episode-steps 10000`` 都不会提高任务自身的原生动作步数上限。``--planner-timeout-s`` 限制每个规划会话的总耗时，包括模型推理和工具调用。

规划器读取 ``robots/robodojo/guides/GUIDE_RPENT.md`` 并使用对应模式的 prompt。探索期间，失败尝试记录保存在运行输出中，工作笔记保存在当前场景的 ``_internal/inbox/<cell>/wip/``。环境判定任务成功后，RPent 保存最后一次尝试中的有效调用到 ``<cell>_recipe.jsonl``。保存内容按调用顺序排列，包括符合导出条件的运动命令，以及返回掩码且未报错的 SAM3 调用。SAM3 返回掩码不代表识别到了正确对象，仍需检查图像。规划器另行写入对应的 ``<cell>.json`` 任务记录，并整理 task-family 和 global 经验草稿。

默认情况下，探索结束后 RPent 保存成功任务的 JSON 记录及配套 JSONL 动作序列到本地 ``task-specific/``。通过格式校验的经验草稿合并到 ``task-family/`` 和 ``global/``，记忆索引 ``MEMORY.md`` 同时更新。使用 ``--no-auto-merge-memory`` 可关闭自动合并，保留输出供手动审核。这些操作只写入本地文件，不会上传到 Hugging Face；公开共享的记忆需在数据集仓库中另行审核。目录结构见 :doc:`../development/memory`。

常用参数
--------

默认由 RPent 在当前 Python 环境中启动仿真、SAM3 和所选 VLA 模型服务。仿真器安装在独立环境时，指定 ``--sim-python``。

使用 ``--task`` 选择任务。固定场景通过 ``--seed`` 选择官方布局组，通过 ``--layout`` 选择组内布局，两者默认均为 ``0``。例如，``--task stack_blocks --seed 0 --layout 2`` 使用第 0 组的第 2 个布局。需要随机生成场景时，添加 ``--random``，此时 ``--layout`` 不生效。

- ``--env-cuda-device``、``--am-cuda-device``、``--sam3-cuda-device``：分别选择本地服务的 GPU；省略时回退到 ``--cuda-device``，再沿用 ``CUDA_VISIBLE_DEVICES``。
- ``--am-backend``：选择动作模型，目前支持 ``vpp2`` 或 ``awomo05``。
- ``--am-checkpoint``：指向包含 ``policy/`` 和 ``checkpoints/`` 的资源根目录，覆盖所选后端的 ``VPP2_MODEL_PATH`` 或 ``AWOMO05_MODEL_PATH``。
- ``--env-endpoint``、``--sam3-endpoint``、``--am-endpoint``：连接已有 RPent RPC 服务；VLA 协议必须匹配所选后端。
- ``--source-root``：使用本地 RoboDojo 源码替代包内源码。

子服务继承当前终端的环境变量；CLI 不会自动读取 ``config/runtime.env``。\
完整参数可运行 ``rpent --robot robodojo --help`` 查看。

规划器可调用的工具
------------------

评测只运行一个回合，不提供 reset；探索模式允许通过 ``reset`` 重试同一场景。Flash 回放仍不可用。

初始观测和运动反馈包含 ``episode_status.step`` （已用原生动作步数）、``step_limit`` （总步数上限）和 ``remaining_steps`` （剩余步数）。
这些计数对应观测保存时的状态；顶层 ``step`` 是观测记录编号。读取历史观测不会消耗动作步数。

``vpp2_act(instruction, chunks=1)`` 执行指定子任务。每个 chunk 预测 32 个双臂 EE16 绝对目标，每臂含 xyz、wxyz 和夹爪。原生 EE 控制执行前 24 步。``chunks=1`` 时返回规划器，继续下一块时重新推理。VPP2 使用初始 RGB 帧和间隔为 25 个动作的 8 个历史采样。策略动作和 Primitive 动作都会更新历史，切换子任务时保留历史；看图和 ``render`` 不增加动作时刻。动作反馈缺失后，策略历史失效，直到 reset；无法 reset 时，需开始新回合才能恢复 VPP2。

选择 Awomo05 后端时，使用 ``awomo05_act(chunks=1)`` 按官方完整任务指令执行双臂关节目标。任务指令取自回合初始观测，在该回合内保持不变。每块执行 8 步并逐步更新观测，下一块重新推理；``chunks`` 限制单次调用的动作块数。模型历史跨调用保留，也包含运动 Primitive 执行后的观测。取消后不续接剩余动作；推理或执行结果不确定时，需检查错误并开始新回合，不应直接重试。

``view_env_state`` 读取保存的图像和状态，``render`` 刷新观测。``sample_world_xyz(view, pixels, step=None, neighborhood=1)`` 查询 [行,列] 像素，默认取 3×3 邻域。``query_world_map`` 查询半开区间 [r0,c0,r1,c1]，默认最多返回 256 个点。view 使用 ``head``、``left_wrist`` 或 ``right_wrist``，必须与选点图像的视角及步号一致。查询读取保存的同帧深度，不暗中刷新；无效深度被排除，返回的是可见表面坐标，不是物体中心。

``segment`` 和 ``back_project`` 也接受 ``step``。分割返回质心 ``centroid_rc`` 和掩码内像素 ``point_rc``；凹形掩码的质心可能在物体外，反投影应优先使用 ``point_rc`` 及返回的 ``step_idx``。这两个工具保留相机名 ``cam_head``、``cam_left_wrist``、``cam_right_wrist``。

调用 ``segment(text_prompt=...)`` 时，描述可见的颜色、形状和位置。工具返回红色掩码叠加图；使用定位点前先检查叠加图，高分不代表选中了正确物体。分割失败时可修改描述，或在同一历史帧中手动选取可见像素查询。叠加图和几何结果保存在对应帧中。使用 ``back_project`` 获取选定掩码内像素的世界坐标。

运动 Primitive 使用原生 cuRobo 位姿规划并执行关节目标。规划器的障碍物模型包含简化桌面，未完整表示场景物体和另一只机械臂；选择路点时应为它们留出空间。

``move_to(arm, xyz, quat=None, gripper=None, substeps=25)`` 使用世界坐标、米及 wxyz 四元数；省略姿态或夹爪参数则保持对应状态／目标。``substeps`` 限制路径抽样数，每个执行的路点消耗一个原生动作步（0.04 秒仿真时间）。Prompt 默认使用 25，较小修正可依次选择 10、5、1；1 只发送最后路点，不会等待到达。``rotate_wrist`` 绕世界 Z 轴相对旋转，单位为度。``final_dist_m`` 是实测位置误差，不是到达保证。检查 ``completed``、``executed_steps`` 和 ``stop_reason``；超时的动作可能已在服务端执行，不会自动重试。

``set_gripper(arm, val, steps=10)`` 使用 0=闭、1=开，``release`` 默认开到 1。中间值表示归一化开度目标，而非物理宽度。反馈读取实测关节状态，夹爪运动期间保持其他关节目标不变。
