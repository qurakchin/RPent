:html_theme.sidebar_secondary.remove:

Time & Token Costs
==================

Reported mean runtime and token usage for the configurations with cost
measurements. The page covers LIBERO-PRO, RoboCasa365 Target50, and RoboTwin; a
missing measurement appears as ``—``, and the table is not a complete ranking.

Costs are not ranked. Compare rows only within the same benchmark, planner
configuration, and hardware. Values come from
``docs/_static/leaderboard/results.json`` and follow the accounting in the
source notes: elapsed time may include failed and timed-out episodes, and token
columns report output tokens or total tokens as the source records them. For
example, Flash Mode reports 60.19 s per episode across the 800 LIBERO-PRO cases,
while Codex + GPT-6 Astra (low) reports 412.14 s.

**Page map:** runtime → tokens → source notes. Recording a new cost row is part
of :doc:`Reproducing a Result <reproduction>`.

.. rpent-leaderboard:: time-token-costs
