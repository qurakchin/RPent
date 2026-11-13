.. _leaderboard-reproduction:

Reproducing a Result
====================

This page lists what a leaderboard row depends on and what to record when you
rerun or submit one. Counting and aggregation rules are in
:doc:`Evaluation Protocol <methodology>`; installation commands are in
:doc:`Quick Start <../get_started/quickstart>` and the platform page.

.. page-head::
   :for: Readers who will rerun a published row or add a new result
   :outcome: You have a checklist for versions, hardware, matrix, success signal, aggregation, cost, and raw data
   :read-when: A reported rate will be reproduced, compared, or submitted
   :skip-when: You only need one task to run; use Quick Start or the platform page

**Page map:** inputs → software and hardware → installation → run matrix →
success signal → aggregation → cost → limits → raw data.

Inputs a row depends on
-----------------------

A row is comparable only when every input below matches. The source record in
``docs/_static/leaderboard/results.json`` is authoritative for what was
actually recorded; an empty field means the source does not state it.

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - Input
     - What it covers
     - Where it is recorded
   * - Benchmark and protocol
     - LIBERO, LIBERO-PRO, RoboCasa365 Target50, or RoboTwin C2R, plus the
       ``protocol_id``.
     - ``results.json`` result row
   * - Task matrix
     - Suites, tasks, and seeds, and therefore the episode denominator.
     - ``episodes`` and the suite tables on :doc:`Performance <performance>`
   * - Checkpoint
     - Model repository, revision, and normalization statistics.
     - Source note; platform page
   * - Planner
     - Backend, model, reasoning effort, turn limit, and timeouts.
     - Configuration row and source note
   * - Memory revision
     - ``--memory-version``, or local memory directory and corpus.
     - Source note; :doc:`memory <../guides/memory>`
   * - Code revision
     - RPent and RLinf commits, when the source identifies them.
     - Source record ``commit`` field
   * - Hardware and software
     - GPU model and count, driver and CUDA build, Python and package
       versions.
     - Source note, when the campaign recorded them

Software and hardware
---------------------

RPent requires Linux, Python 3.11, and an NVIDIA GPU; the LIBERO-PRO example
uses about 60 GB of disk and 16 GB of GPU memory. Record the GPU model and
count, driver version, PyTorch CUDA build, and the RPent and RLinf commits with
the run. The leaderboard does not backfill these fields: rows whose source does
not state hardware stay blank, and their times are comparable only within that
source.

Installation
------------

Complete :doc:`Quick Start <../get_started/quickstart>` for the base
environment, then follow the platform page for its extra, assets, and
checkpoint. Do not mix LIBERO variants in one Python environment; each of
``standard``, ``pro``, and ``plus`` has its own extra and assets command.

Run matrix
----------

The published denominators are fixed by the protocol:

- LIBERO: four suites, 100 episodes each (400).
- LIBERO-PRO: eight suites, tasks 0–9 and seeds 0–9, 100 episodes each (800).
- RoboCasa365 Target50: 50 tasks, 340 episodes (18 atomic × 10, 16 seen
  composite × 5, 16 unseen composite × 5).
- RoboTwin C2R: 50 tasks × 5 verified seeds (250).

Run one episode per command and keep one output directory per episode. A
partial matrix may be reported, but it is not the published denominator; state
which suites and seeds ran.

Success signal
--------------

Use the environment's native signal: ``terminated`` for LIBERO and LIBERO-PRO,
the Target50 success flag for RoboCasa365, and ``TASK_ENV.eval_success`` for
RoboTwin. On a real robot, an operator confirms the outcome. A planner
``finish``, a timeout, a saved transcript, or a video is not a success.

Record the retry and timeout settings with the run: ``--max-turns``,
``--max-episode-steps``, ``--planner-timeout-s``, and any per-model timeout.
An episode that times out counts as a failure. If an episode never produced an
environment outcome because a service failed, rerun it and note the rerun in
the source record; do not count both attempts.

Aggregation
-----------

Keep per-suite and per-task counts, then aggregate as the protocol defines.
LIBERO and LIBERO-PRO Overall are unweighted means of suite rates; RoboCasa365
Target50 Overall is the mean of 50 task rates, not the pooled fraction;
RoboTwin reports one rate over 250 episodes. A derived row must name the rows
it combines.

Cost
----

Measure runtime and tokens in a separate run or from the recorded transcript;
do not estimate them from success rates. Report the mean per episode, state
whether failed and timed-out episodes are included, and name the token
definition (output tokens or total tokens). Time comparisons hold only within
the same benchmark, planner configuration, and hardware.

Limits
------

- One successful episode validates installation and the execution path, not
  benchmark performance.
- A reproduced suite rate can differ from the published value through seed
  coverage, memory revision, or a new code commit; report the difference, not
  only the headline.
- External baselines are transcribed, not rerun by RPent; their protocol may
  differ.

Raw data
--------

Archive the per-episode ``result.json``, ``transcript_*.json``, and ``run.log``
with the run, plus the commands and environment variables used. Put the archive
hash in the source record and list the commit, checkpoint, denominator, and
per-task results. The leaderboard renders whatever the record states; it does
not infer missing counts.
