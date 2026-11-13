.. _leaderboard-reproduction:

复现一条成绩
====================

本页列出排行榜一行所依赖的输入，以及重跑或提交结果时需要记录的内容。计数与汇总规则见
:doc:`评测协议 <methodology>`；安装命令见 :doc:`快速开始 <../get_started/quickstart>`
和对应平台页。

.. page-head::
   :for: 要重跑已发布成绩，或向排行榜提交新结果的读者
   :outcome: 拿到版本、硬件、任务矩阵、成功判定、汇总、开销和原始数据的核对清单
   :read-when: 要复现、比较或提交一条成绩时
   :skip-when: 只想跑通一个任务；直接用快速开始或平台页

**本文结构：** 依赖输入 → 软件与硬件 → 安装 → 任务矩阵 → 成功判定 → 汇总 →
开销 → 限制 → 原始数据。

依赖输入
--------

只有下列输入全部一致，两行成绩才可比。``docs/_static/leaderboard/results.json``
中的来源记录是实际记录内容的权威来源；字段为空表示来源没有写明。

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - 输入
     - 内容
     - 记录位置
   * - 基准与协议
     - LIBERO、LIBERO-PRO、RoboCasa365 Target50 或 RoboTwin C2R，以及
       ``protocol_id``。
     - ``results.json`` 的结果行
   * - 任务矩阵
     - 套件、任务和 seed，由此决定回合分母。
     - ``episodes`` 与 :doc:`评测成绩 <performance>` 的套件表
   * - Checkpoint
     - 模型仓库、revision 和归一化统计文件。
     - 来源注释；平台页
   * - 规划器
     - 后端、模型、推理强度、轮数上限和超时。
     - 配置行和来源注释
   * - 记忆版本
     - ``--memory-version``，或本地记忆目录与语料。
     - 来源注释；:doc:`记忆 <../guides/memory>`
   * - 代码版本
     - 来源标明时的 RPent 与 RLinf commit。
     - 来源记录的 ``commit`` 字段
   * - 硬件与软件
     - GPU 型号与数量、驱动和 CUDA 构建、Python 与依赖版本。
     - 评测批次记录时的来源注释

软件与硬件
----------

RPent 需要 Linux、Python 3.11 和 NVIDIA GPU；LIBERO-PRO 示例约占 60 GB 磁盘和
16 GB 显存。请随运行记录 GPU 型号与数量、驱动版本、PyTorch CUDA 构建，以及
RPent 和 RLinf 的 commit。排行榜不会补填这些字段：来源未写明硬件的行保持空白，
其耗时只能在同一来源内部比较。

安装
----

先按 :doc:`快速开始 <../get_started/quickstart>` 准备基础环境，再按平台页安装对应
extra、资源和 checkpoint。不要在同一 Python 环境中混装 LIBERO 版本；``standard``、
``pro`` 和 ``plus`` 各有自己的 extra 与资源下载命令。

任务矩阵
--------

已发布的分母由协议固定：

- LIBERO：4 个套件，每个 100 个回合（400）。
- LIBERO-PRO：8 个套件，任务 0–9、seed 0–9，每个 100 个回合（800）。
- RoboCasa365 Target50：50 个任务，340 个回合（18 个原子任务 × 10，16 个
  seen 组合任务 × 5，16 个 unseen 组合任务 × 5）。
- RoboTwin C2R：50 个任务 × 5 个已验证 seed（250）。

每条命令只跑一个回合，每个回合使用独立的输出目录。可以报告部分矩阵，但它不是
已发布的分母；请写明实际运行的套件和 seed。

成功判定
--------

使用环境原生判定：LIBERO 与 LIBERO-PRO 看 ``terminated``，RoboCasa365 看
Target50 的成功标志，RoboTwin 看 ``TASK_ENV.eval_success``。真机由操作员确认结果。
规划器 ``finish``、超时、保存的 transcript 或录像都不算成功。

随运行记录重试与超时设置：``--max-turns``、``--max-episode-steps``、
``--planner-timeout-s``，以及模型专属超时。超时回合计为失败。如果某个回合因服务
故障从未产生环境判定，请重跑并在来源记录中注明；两次尝试不能同时计数。

汇总
----

保留套件级和任务级计数，再按协议汇总。LIBERO 与 LIBERO-PRO 的 Overall 是各套件
成功率的等权平均。RoboCasa365 Target50 的 Overall 是 50 个任务成功率的平均，不是
合并后的成功比例。RoboTwin 报告 250 个回合上的一个成功率。派生行必须注明它合并
了哪些行。

开销
----

单独测量运行时间和 Token，或从记录的 transcript 统计；不要用成功率推算。报告每
回合平均值，写明是否包含失败与超时回合，并说明 Token 口径（输出 Token 或总
Token）。耗时只在同一基准、同一规划器配置和同一硬件条件下可比。

限制
----

- 单个回合成功只能验证安装和执行链路，不能代表基准成绩。
- 复现的套件成绩可能因 seed 覆盖、记忆版本或新的代码 commit 与发布值不同；请报告
  差异，而不只是总分。
- 外部基线是转录值，RPent 未重跑；其协议可能不同。

原始数据
--------

归档每个回合的 ``result.json``、``transcript_*.json`` 和 ``run.log``，以及使用的
命令和环境变量。把归档哈希写入来源记录，并列出 commit、checkpoint、分母和逐任务
结果。排行榜只渲染记录中写明的内容，不会反推缺失的计数。
