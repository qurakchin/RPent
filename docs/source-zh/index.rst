.. _home:

欢迎使用 RPent
==================

.. image:: https://raw.githubusercontent.com/RLinf/misc/main/pic/rpent_logo.png
   :alt: RPent
   :class: rpent-home-logo

RPent（Recursive Physical Agent）是一个开源框架，用于构建在物理世界交互中积累经验、改进行为的具身智能体。它不限定基础模型，将感知（perception）、推理（reasoning）、记忆（memory）、执行（execution）和自我演进（self-evolution）整合到统一的智能体循环中。

RPent 面向机器人学与具身智能的研究者和工程师：用同一套评测流程比较基础模型、规划器和记忆策略，或在仿真与真机上运行同一个智能体循环。读完 :doc:`快速开始 <rst_source/get_started/quickstart>`，你会完成安装、跑通一个 LIBERO-PRO 任务，并找到它的结果文件。

.. button-ref:: rst_source/get_started/quickstart
   :ref-type: doc
   :color: primary
   :shadow:
   :expand:

   安装 RPent 并运行第一个任务

.. grid:: 1 2 2 2
   :gutter: 3

   .. grid-item-card:: 1. 跑一个任务
      :link: rst_source/get_started/quickstart
      :link-type: doc

      先读 :doc:`快速开始 <rst_source/get_started/quickstart>`，再进入
      :doc:`LIBERO <rst_source/simulators/libero>`、
      :doc:`RoboCasa365 <rst_source/simulators/robocasa>`、
      :doc:`RoboTwin <rst_source/simulators/robotwin>` 或
      :doc:`RoboDojo <rst_source/simulators/robodojo>`。真机部署见
      :doc:`单臂 Franka <rst_source/real_world_robots/franka>`、
      :doc:`双臂 Franka <rst_source/real_world_robots/dual_franka>` 和
      :doc:`YAM <rst_source/real_world_robots/yam>`，任务视频见
      :doc:`真实世界演示 <rst_source/real_world_demos/franka>`。

   .. grid-item-card:: 2. 比较结果
      :link: rst_source/leaderboard/index
      :link-type: doc

      阅读 :doc:`评测成绩 <rst_source/leaderboard/performance>`、
      :doc:`评测协议 <rst_source/leaderboard/methodology>` 和
      :doc:`耗时与 Token 开销 <rst_source/leaderboard/time-token-costs>`。

   .. grid-item-card:: 3. 配置智能体
      :link: rst_source/guides/memory
      :link-type: doc

      配置 :doc:`记忆 <rst_source/guides/memory>`、
      :doc:`工具 <rst_source/guides/configure_primitives>`、
      :doc:`规划器 <rst_source/guides/configure_planner>`、
      :doc:`命令行 <rst_source/guides/cli>`、
      :doc:`Dashboard <rst_source/guides/dashboard>`、
      :doc:`Flash 模式 <rst_source/guides/flash>`、
      :doc:`数据飞轮 <rst_source/guides/flywheel>` 或
      :doc:`远程服务 <rst_source/guides/advanced_deployment>`。

   .. grid-item-card:: 4. 理解与扩展
      :link: rst_source/development/architecture
      :link-type: doc

      先读 :doc:`系统架构 <rst_source/development/architecture>`，再
      :doc:`添加机器人 <rst_source/development/add_robot>`、
      :doc:`动作原语 <rst_source/development/add_primitive>`、
      :doc:`动作模型 <rst_source/development/add_action_model>` 或
      :doc:`规划器 <rst_source/development/add_planner>`。背景见
      :doc:`Harness VLA <rst_source/resources/harnessvla>`。

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 开始使用

   RPent 简介 <rst_source/get_started/overview>
   快速开始 <rst_source/get_started/quickstart>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 仿真环境

   LIBERO <rst_source/simulators/libero>
   RoboCasa365 <rst_source/simulators/robocasa>
   RoboTwin <rst_source/simulators/robotwin>
   RoboDojo <rst_source/simulators/robodojo>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 真实机器人

   单臂 Franka <rst_source/real_world_robots/franka>
   双臂 Franka <rst_source/real_world_robots/dual_franka>
   YAM <rst_source/real_world_robots/yam>
   SO-101 <rst_source/real_world_robots/so101>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 真实世界演示

   双臂 Franka <rst_source/real_world_demos/franka>
   YAM <rst_source/real_world_demos/yam>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 排行榜

   评测成绩 <rst_source/leaderboard/performance>
   评测协议 <rst_source/leaderboard/methodology>
   耗时与 Token 开销 <rst_source/leaderboard/time-token-costs>
   复现一条成绩 <rst_source/leaderboard/reproduction>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 使用指南

   记忆与探索 <rst_source/guides/memory>
   动作原语与工具 <rst_source/guides/configure_primitives>
   规划器配置 <rst_source/guides/configure_planner>
   命令行参考 <rst_source/guides/cli>
   交互使用 <rst_source/guides/dashboard>
   Flash 模式 <rst_source/guides/flash>
   数据飞轮 <rst_source/guides/flywheel>
   远程服务与并行运行 <rst_source/guides/advanced_deployment>
   问题排查 <rst_source/guides/troubleshooting>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 原理与开发

   系统架构与执行流程 <rst_source/development/architecture>
   核心接口 <rst_source/development/interfaces>
   记忆机制 <rst_source/development/memory>
   添加机器人或仿真环境 <rst_source/development/add_robot>
   添加动作原语 <rst_source/development/add_primitive>
   添加动作模型 <rst_source/development/add_action_model>
   添加规划器 <rst_source/development/add_planner>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: 项目资源

   Harness VLA <rst_source/resources/harnessvla>
   贡献指南 <rst_source/resources/contributing>
   v0.1 发布说明 <rst_source/resources/release_v0.1>

.. toctree::
   :maxdepth: 1
   :hidden:

   动作模型参考 <rst_source/development/action_model_reference>
   机器人接入参考 <rst_source/development/add_robot_reference>
   双臂 Franka 参考 <rst_source/real_world_robots/dual_franka_reference>
   RoboDojo 参考 <rst_source/simulators/robodojo_reference>
