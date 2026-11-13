RPent 简介
============

本页介绍框架的定位、评测覆盖和已支持的平台；安装与首次运行见 :doc:`quickstart`。

.. page-head::
   :for: 判断 RPent 是否适合自己、以及该从哪个平台入手的读者
   :outcome: 能说明智能体循环、评测覆盖，并确定下一页该读什么
   :read-when: 初次接触 RPent，或在仿真环境与真机之间做选择时
   :skip-when: 只想安装并跑通任务；直接看 :doc:`quickstart`

**本文结构：** 框架与设计原则 → 成绩看哪里 → 从哪类平台入手 → 规划器选择。

RPent（Recursive Physical Agent）是一个开源框架。它用于构建具身智能体：在物理世界交互中积累经验，并据此改进行为。RPent 不绑定单一基础模型。它把感知、推理、记忆、执行和自我演进放进同一个智能体循环，并通过统一接口连接。更换或组合模型、规划器和机器人服务时，不需要重写整套流程。智能体在持续交互中不断反思和调整，从而获得初始设计之外的新能力。

Pent 这个名字源自五芒星（Pentagram），其五个顶点象征多模态智能融合为一个统一的具身智能体。中心的无穷符号（∞）代表感知、推理、执行和自我演进的递归循环，让智能持续向物理世界扩展。

.. image:: ../../../_static/img/architecture-zh.svg
   :alt: RPent 分层结构：用户层、智能体层、模型与环境服务以及环境层
   :width: 100%

RPent 的三条核心设计原则是服务化、标准化和可组合（service-oriented, standardized, and composable）。各种能力以可复用服务的形式部署，通过统一接口连接，再组合成不同的物理智能体。

排行榜
------

RPent 报告 LIBERO、LIBERO-PRO、RoboCasa365 Target50 和 RoboTwin C2R 上的成功率。
:doc:`排行榜 <../leaderboard/index>` 收录图表、各基准的表格、每行结果对应的模型配置和来源；
:doc:`耗时与 Token 开销 <../leaderboard/time-token-costs>` 给出同一批配置的运行时间和 Token 用量。

选择平台
------------

平台分为两类，各有一个索引页做横向比较，再由具体页面负责安装与运行：

- :doc:`仿真环境 <../simulators/index>`：LIBERO、RoboCasa365、RoboTwin 和 RoboDojo。
  每个平台有各自的 extra、checkpoint 和复现命令。
- :doc:`真实机器人 <../real_world_robots/index>`：单臂和双臂 Franka、YAM，含硬件、标定与安全步骤。
  SO-101 仅作说明，目前没有适配器。

安装和第一个 LIBERO-PRO 任务见 :doc:`quickstart`，之后打开所用平台的页面。研究背景见 :doc:`../resources/harnessvla`。

规划器
------

规划器可选择 ``api``、``claude_code`` 或 ``codex``；LIBERO 还提供用于执行已有计划的
:doc:`Flash Mode <../guides/flash>`。模型服务配置见 :doc:`../guides/configure_planner`。

DreamZero 是计划中的 WAM 后端，尚未集成，暂无使用文档。
