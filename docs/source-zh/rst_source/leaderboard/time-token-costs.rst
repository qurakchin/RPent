:html_theme.sidebar_secondary.remove:

耗时与 Token 开销
========================

本页列出已有开销数据的配置的平均耗时与 Token 用量。评测覆盖 LIBERO-PRO、RoboCasa365 Target50 和 RoboTwin；未报告的数值显示为 ``—``，该表不是完整排名。

开销不做排名。只应在同一基准、同一规划器配置和同一硬件条件下比较各行。数值来自 ``docs/_static/leaderboard/results.json``，并沿用来源注释中的统计口径：耗时可能包含失败和超时回合，Token 列按来源记录的是输出 Token 或总 Token。例如，Flash Mode 在 LIBERO-PRO 的 800 个回合上平均每回合 60.19 秒，Codex + GPT-6 Astra（low）为 412.14 秒。

.. rpent-leaderboard:: time-token-costs
