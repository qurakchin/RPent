:html_theme.sidebar_secondary.remove:

评测成绩
========

本页列出 RPent 及各表中基线的任务成功率。评测覆盖 LIBERO、LIBERO-PRO、RoboCasa365 Target50 和 RoboTwin C2R 四个基准。前两者分别有 4 个和 8 个套件。Target50 含 50 个任务，Overall 按任务等权。排名仅限图中方法及评测范围。外部基线转录自所引论文表格或项目页面，RPent 未对其重新评测。环境配置与复现命令见 :doc:`LIBERO <../simulators/libero>`、:doc:`RoboCasa365 <../simulators/robocasa>` 和 :doc:`RoboTwin <../simulators/robotwin>` 教程。

所有数值由 ``docs/_static/leaderboard/results.json`` 渲染。该文件记录每条结果的来源和协议，表下注释说明各套件的额外口径。`数据来源` 一节列出所有引用的记录，来源标明仓库提交时同时列出 commit。计数、汇总和推算规则见 :doc:`评测协议 <methodology>`。

代表性成绩：

- RPent + GPT-6 Astra（low）：LIBERO-PRO 92.63%（741/800）。
- Opus-4.7（max）：LIBERO 96.00%（384/400）。
- GPT-6 Astra（high）：RoboCasa365 Target50 59.20%（340 个回合）。
- GPT-5.5（xhigh）：RoboTwin C2R 62.40%（156/250）。

可切换视图查看套件级成绩，打开表格视图查看精确计数和回合覆盖。同一批配置的耗时与 Token 数据见 :doc:`耗时与 Token 开销 <time-token-costs>`。

**本文结构：** 代表性成绩 → 套件表 → 来源记录 → 协议。要重跑某一行，从
:doc:`复现一条成绩 <reproduction>` 开始。

.. rpent-leaderboard:: performance
