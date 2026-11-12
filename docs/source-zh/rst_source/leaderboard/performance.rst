:html_theme.sidebar_secondary.remove:

评测成绩
========

本页列出 RPent 及各表中基线的任务成功率。评测覆盖 LIBERO（4 个套件）、LIBERO-PRO（8 个套件）、RoboCasa365 Target50（50 个任务，Overall 按任务等权）和 RoboTwin C2R。排名仅限图中方法及评测范围；外部基线转录自所引论文表格或项目页面，RPent 未对其重新评测。环境配置与复现命令见 :doc:`LIBERO <../simulators/libero>`、:doc:`RoboCasa365 <../simulators/robocasa>` 和 :doc:`RoboTwin <../simulators/robotwin>` 教程。

所有数值由 ``docs/_static/leaderboard/results.json`` 渲染，该文件记录每条结果的来源和协议；表下注释说明各套件的额外口径。代表性成绩包括：RPent + GPT-6 Astra（low）在 LIBERO-PRO 上 92.63%（741/800），Opus-4.7（max）在 LIBERO 上 96.00%（384/400），GPT-6 Astra（high）在 RoboCasa365 Target50 的 340 个评测回合上达到 59.20%，GPT-5.5（xhigh）在 RoboTwin C2R 上 62.40%（156/250）。可切换视图查看套件级成绩，打开表格视图查看精确计数和回合覆盖。同一批配置的耗时与 Token 数据见 :doc:`耗时与 Token 开销 <time-token-costs>`。

.. rpent-leaderboard:: performance
