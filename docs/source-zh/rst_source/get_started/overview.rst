RPent 简介
============

**RPent（Recursive Physical Agent）** 是一个开源具身智能体框架，让智能体在与物理世界的递归交互中持续演进。它不绑定单一基础模型，而是将感知、推理、记忆、执行与自我演进整合进统一架构。智能体据此在交互与反思中习得新能力。

Pent 源自五芒星（Pentagram），五个顶点对应感知、推理、记忆、执行和自我演进；中心的无穷符号（∞）表示五者之间的递归循环。

.. image:: https://raw.githubusercontent.com/RLinf/misc/main/pic/rpent_framework.png
   :alt: RPent 规划、感知、记忆和执行架构
   :width: 100%

RPent 遵循三条设计原则：**服务化、标准化、可组合**\ （service-oriented, standardized, and composable）。各项能力以独立服务运行并通过统一接口连接，便于在不同仿真器、模型和真机上按需组合与扩展。

排行榜
------

对比 LIBERO、LIBERO-PRO、RoboCasa365 Target50 和 RoboTwin C2R 上的成功率。
排名仅限图中方法及评测范围；完整结果、模型配置和来源见 :doc:`../leaderboard/index`。

.. raw:: html

   <a href="../leaderboard/index.html">
     <img class="only-light" src="../../_static/leaderboard/leaderboard-zh-light.svg" alt="RPent 排行榜" width="100%">
     <img class="only-dark" src="../../_static/leaderboard/leaderboard-zh-dark.svg" alt="RPent 排行榜" width="100%">
   </a>

选择平台
------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 平台
     - 文档内容
   * - :doc:`LIBERO <../simulators/libero>`
     - Pi0.5、SAM3、LIBERO / LIBERO-PRO 运行与复现。
   * - :doc:`RoboCasa365 <../simulators/robocasa>`
     - RLDX-1、厨房任务和 Target50 复现。
   * - :doc:`RoboTwin <../simulators/robotwin>`
     - LingBot-VLA、双臂仿真任务和 C2R 复现。
   * - :doc:`RoboDojo <../simulators/robodojo>`
     - Isaac Sim 双臂 ARX-X5 操作，支持 VPP2 与 Awomo05 策略。
   * - :doc:`RoboLab <../simulators/robolab>`
     - RLinf RoboLab Isaac Sim 仿真环境与策略部署。
   * - :doc:`EFE <../simulators/efe>`
     - 通过 Harbor 运行 Embodied First Exam（EFE）任务，支持 Skills 或原生动作。
   * - :doc:`单臂 Franka <../real_world_robots/franka>`
     - 硬件准备、标定、自检和运行。
   * - :doc:`双臂 Franka <../real_world_robots/dual_franka>`
     - 双节点部署、操作与人工参与的探索。
   * - :doc:`YAM <../real_world_robots/yam>`
     - 双臂双机部署、手动技能测试与任务运行。
   * - :doc:`SO-101 <../real_world_robots/so101>`
     - 规划中（暂未支持）。

在线规划器可选择 ``api``、``claude_code``、``codex``、``gemini_cli`` 或 ``opencode``；LIBERO 还提供用于执行已有计划的 :doc:`Flash Mode <../guides/flash>`。模型服务配置见 :doc:`../guides/configure_planner`。

从 :doc:`quickstart` 开始运行第一个任务。评测成绩和资源开销见 :doc:`../leaderboard/index`，研究背景见 :doc:`../resources/harnessvla`。
Cosmos Policy、Fast-WAM 和 UniWAM 等 WAM 后端的使用方法见 :doc:`../simulators/libero` 与 :doc:`../development/add_action_model`；DreamZero 仍在规划中，暂无使用文档。
