
.. _leaderboard-protocol:

Evaluation Protocol
===================

This page defines what the leaderboard counts and how it reports coverage, so
two rates are comparable only when their protocol identifiers match. Commands
and per-environment success signals are in the simulator guides; this page
covers counting and reporting. Results are rendered from
``docs/_static/leaderboard/results.json``.

.. page-head::
   :for: Readers comparing reported rates or adding a result to the leaderboard
   :outcome: You can tell whether two rates are comparable and how counts and aggregates are derived
   :read-when: You are reading a success rate, adding a result, or checking denominators
   :skip-when: You only need to run a task; the platform page states its own success signal

**Page map:** success → episodes and denominators → retries and timeouts →
aggregation → counts and estimates → what a result records → provenance →
runtime and tokens → reproduction.

Success
-------

A success is an episode for which the environment's native signal reports
success, or, on a real robot, an operator confirms the outcome. A planner
``finish``, a saved transcript, or a recorded video does not establish success.

- :doc:`LIBERO and LIBERO-PRO <../simulators/libero>`: the final state's
  top-level ``terminated`` value.
- :doc:`RoboCasa365 <../simulators/robocasa>`: the environment's native success
  flag for the selected Target50 task.
- :doc:`RoboTwin <../simulators/robotwin>`: ``TASK_ENV.eval_success``. Planner
  completion and episode timeouts are separate outcomes.

Episodes and denominators
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 58 20

   * - Benchmark
     - Composition
     - Episodes
   * - LIBERO (standard)
     - Four suites, 100 episodes per suite.
     - 400
   * - LIBERO-PRO
     - Spatial, Object, Goal, and Long (the ``libero_10`` family), each with
       task and swap suites; 100 episodes per suite (tasks 0–9, seeds 0–9).
     - 800
   * - RoboCasa365 Target50
     - 50 tasks: 18 atomic tasks × 10, 16 composite seen × 5, 16 composite
       unseen × 5.
     - 340
   * - RoboTwin C2R
     - 50 tasks × 5 verified seeds.
     - 250

Aggregation
-----------

- LIBERO Overall and LIBERO-PRO Overall are unweighted means of the four and
  eight suite rates. Every LIBERO-PRO suite has the same denominator, so the
  Overall also equals the pooled successes divided by episodes.
- RoboCasa365 Target50 Overall is the mean of the 50 task success rates. It is
  not the pooled fraction of successful episodes, so the two values can differ.
- RoboTwin C2R reports one aggregate over 250 episodes.

A row with ``status: derived`` is computed from component rows and is not an
independent run. Its calculation is recorded in ``results.json``.

Retries and timeouts
--------------------

An episode that times out counts once, as a failure. An episode that never
produced an environment outcome because a service failed may be rerun; the
source record notes the rerun, and only the completed attempt is counted. The
leaderboard does not record retry counts for sources that do not state them.

Counts and estimates
--------------------

A cell shows ``successes/episodes`` only when the source records both. When a
source publishes a rounded rate without a count, the leaderboard may display
``≈successes/episodes``: the count is the rounded rate multiplied by the
denominator, not a number the source reports. A rate with no denominator means
the source does not state its episode count, and no count is inferred in either
direction.

External baselines are transcribed from the cited paper tables or project
pages; RPent has not re-run them. Their protocol may differ from RPent's, so
read the source notes before comparing rows.

What a result records
---------------------

A result is comparable only when it names the input set in
:doc:`Reproducing a Result <reproduction>`: benchmark and protocol, task matrix
and denominator, checkpoint, planner configuration, memory revision, code
commit, hardware, and retry and timeout settings. ``results.json`` stores the
fields the source provides and leaves the rest empty; it does not infer them.

Provenance
----------

Every success-rate result carries ``source_ids`` and ``protocol_id`` fields in
``results.json``, and the cost rows use the same source records. The Sources
section on :doc:`Performance <performance>` lists
each cited record with its type and URL, and a commit when the record
identifies a repository revision. Contributor archives and experiment reports
that have no public URL are identified by their record ID; their notes state
the artifact or measurement scope.

Runtime and token results
-------------------------

The :doc:`Time & Token Costs <time-token-costs>` page uses the same source
records. Elapsed time is a mean per episode and may include failed and
timed-out episodes. Token columns report evaluation-stage output or total
tokens as the source defines them. Compare costs only within the same
benchmark, planner configuration, and hardware; the leaderboard does not record
hardware for every source.

Reproduction
------------

:doc:`Reproducing a Result <reproduction>` turns one row into a checklist of
versions, hardware, matrix, success signal, aggregation, cost, and raw data.
Each simulator guide documents its reproduction command. A single successful
episode validates the installation and execution path, not benchmark
performance.
