
.. _leaderboard-protocol:

评测协议
========

本页说明排行榜如何计数、如何标注覆盖范围；只有协议标识一致时，两个成功率才可直接比较。各环境的运行命令和成功判定见对应仿真页，本页只说明计数与报告口径。数据由 ``docs/_static/leaderboard/results.json`` 渲染。

**本文结构：** 成功判定 → 回合与分母 → 汇总方式 → 计数与推算 → 来源与版本 → 耗时与 Token → 复现。

成功判定
--------

只有环境原生信号判定成功，或真机操作员确认成功的回合才计为成功。规划器调用 ``finish``、保存对话或生成录像都不能作为成功依据。

- :doc:`LIBERO 与 LIBERO-PRO <../simulators/libero>`：最终状态的顶层 ``terminated`` 值。
- :doc:`RoboCasa365 <../simulators/robocasa>`：所选 Target50 任务的环境原生成功标记。
- :doc:`RoboTwin <../simulators/robotwin>`：``TASK_ENV.eval_success``。规划器完成和回合超时是分开的结果。

回合与分母
----------

.. list-table::
   :header-rows: 1
   :widths: 22 58 20

   * - 基准
     - 组成
     - 回合数
   * - LIBERO（标准）
     - 4 个套件，每套 100 个回合。
     - 400
   * - LIBERO-PRO
     - Spatial、Object、Goal 和 Long（即 ``libero_10`` 任务族），各自包含 task 与 swap 套件；每套 100 个回合（task 0–9、seed 0–9）。
     - 800
   * - RoboCasa365 Target50
     - 50 个任务：18 个 atomic 任务 × 10，16 个 composite seen × 5，16 个 composite unseen × 5。
     - 340
   * - RoboTwin C2R
     - 50 个任务 × 5 个已验证 seed。
     - 250

汇总方式
--------

- LIBERO 和 LIBERO-PRO 的 Overall 分别是 4 个和 8 个套件成功率的算术平均。LIBERO-PRO 各套件分母相同，因此 Overall 也等于成功回合总数除以回合总数。
- RoboCasa365 Target50 的 Overall 是 50 个任务成功率的平均，不是成功回合占全部回合的比例，因此两者可能不同。
- RoboTwin C2R 在 250 个回合上给出一个汇总成绩。

``status: derived`` 的行由分项结果计算得到，不是独立评测；计算方式记录在 ``results.json`` 中。

计数与推算
----------

只有当来源同时记录成功数和回合数时，表格才显示 ``成功数/回合数``。来源只给出取整成功率时，排行榜可能显示 ``≈成功数/回合数``：该计数是取整成功率乘以分母得到的推算值，不是来源报告的原始计数。没有分母表示来源未说明回合数，文档不会据此推算成功数。

外部基线转录自所引论文表格或项目页面，RPent 未重新评测。其协议可能与 RPent 不同，比较前请阅读来源注释。

来源与版本
----------

每条成功率结果在 ``results.json`` 中都有 ``source_ids`` 和 ``protocol_id``，耗时记录使用同一组来源记录。 :doc:`评测成绩 <performance>` 的“数据来源”一节列出每条引用记录的类型和 URL；来源标明仓库提交时同时列出 commit。没有公开 URL 的贡献者归档和实验报告以记录 ID 标识，其注释说明对应的产物或测量范围。

耗时与 Token
------------

:doc:`耗时与 Token 开销 <time-token-costs>` 使用相同的来源记录。耗时是平均每回合时间，可能包含失败和超时回合。Token 列按来源的定义报告评测阶段输出或总 token。只能在相同基准、相同规划器配置和相同硬件上比较开销；排行榜并未记录每个来源的硬件。

复现
----

各仿真页给出复现命令和评测矩阵。复现公布成绩需要相同的 checkpoint、memory revision、seed 矩阵和成功判定。单个回合成功只验证安装和执行链路，不构成基准性能验证。
