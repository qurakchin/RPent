:html_theme.sidebar_secondary.remove:

Performance
===========

Reported success rates for RPent and the baselines listed in each table. The
page covers LIBERO (four suites), LIBERO-PRO (eight suites), RoboCasa365
Target50 (50 tasks, with Overall weighted equally by task), and RoboTwin C2R.
Rankings cover only the methods and evaluation coverage shown; external
baselines are transcribed from the cited paper tables or project pages, not
re-run by RPent. Environment setup and reproduction commands are in the
:doc:`LIBERO <../simulators/libero>`, :doc:`RoboCasa365 <../simulators/robocasa>`,
and :doc:`RoboTwin <../simulators/robotwin>` guides.

All values are rendered from ``docs/_static/leaderboard/results.json``, which
records source and protocol identifiers for each result, and the notes below
the tables state suite-specific caveats. Headline results include 92.63% (741/800) on
LIBERO-PRO for RPent with GPT-6 Astra (low), 96.00% (384/400) on LIBERO for
Opus-4.7 (max), 59.20% over 340 evaluated episodes on RoboCasa365 Target50 for
GPT-6 Astra (high), and 62.40% (156/250) on RoboTwin C2R for GPT-5.5 (xhigh).
Switch views for suite-level results, and open the table view for exact counts
and episode coverage. :doc:`Time & Token Costs <time-token-costs>` reports the
runtime and token measurements for the same configurations.

.. rpent-leaderboard:: performance
