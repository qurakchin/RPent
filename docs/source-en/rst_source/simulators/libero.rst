LIBERO
============

.. figure:: https://raw.githubusercontent.com/Lifelong-Robot-Learning/LIBERO/master/images/fig1.png
   :alt: LIBERO environment overview
   :width: 90%
   :align: center

   LIBERO benchmark overview. Source: `LIBERO project <https://libero-project.github.io/>`_.

Run tabletop manipulation tasks with RPent in `LIBERO <https://libero-project.github.io/>`_, then reproduce LIBERO-PRO experiments. The simulator uses MuJoCo/robosuite. RPent supports the ``standard``, ``pro``, and ``plus`` variants and uses Pi0.5 as the default VLA.

For a first run, follow :doc:`../get_started/quickstart`; this page covers variants, task selection, results, and reproduction.

.. page-head::
   :for: Readers running LIBERO, LIBERO-PRO, or LIBERO-plus tasks and reproducing published rates
   :outcome: You can install a variant, prepare Pi0.5 and SAM3, run a task, and read its result against the native success signal
   :read-when: You are moving beyond the Quick Start's single LIBERO-PRO task, or selecting variants and tasks
   :skip-when: You have not installed RPent yet; complete :doc:`../get_started/quickstart` first

**Page map:** Overview → Installation → VLA Configuration → SAM3 Configuration → Run a Task → View Results → Task Selection → WAM Evaluation → Tasks → Task Memory → Experiment Reproduction → Tools the Planner Can Call.

.. _libero-overview:

Overview
------------

Check the model, task, and runtime requirements before following the installation and run steps.

.. grid:: 2 4 4 4
   :gutter: 2

   .. grid-item-card:: Action Models

      Pi0.5; Cosmos Policy, Cosmos3 and Fast-WAM for standard/Pro evaluation.

   .. grid-item-card:: Planners

      ``api``, ``claude_code``, ``codex``; also see :doc:`../guides/flash`.

   .. grid-item-card:: Tasks

      Object, Goal, Spatial, LIBERO-10

   .. grid-item-card:: Hardware

      Linux, NVIDIA GPU; Python 3.11; CUDA and EGL.

.. _installation-and-variants:

Installation
------------

For a first LIBERO-PRO run, complete the installation, asset downloads, and model setup in :doc:`../get_started/quickstart`. That page also lists estimated GPU memory, disk, and runtime.

For another variant, install the matching extra in an isolated environment and download its assets. Install only one LIBERO variant per Python environment:

.. list-table::
   :header-rows: 1

   * - Variant
     - Install
     - Assets
   * - ``standard``
     - ``uv pip install -e ".[libero]"``
     - ``libero-download-assets --skip-existing``
   * - ``pro``
     - ``uv pip install -e ".[libero-pro]"``
     - ``liberopro-download-assets --skip-existing``
   * - ``plus``
     - ``uv pip install -e ".[libero-plus]"``
     - ``liberoplus-download-assets --skip-existing``

Each extra includes Pi0.5 (``rpent-openpi``), SAM3, and the RLinf runtime
(``rlinf``). Download model weights separately as described below.

At runtime, set ``--libero-type`` to match the installed variant.

VLA Configuration
-----------------

Download the recommended SFT checkpoint
`RLinf-Pi05-LIBERO-130-fullshot-SFT
<https://huggingface.co/RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT>`_,
then point at it via ``PI05_CHECKPOINT_PATH``:

.. code-block:: bash

   hf download RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT \
     --local-dir /path/to/rlinf-pi05-libero-130-fullshot-sft

   export PI05_CHECKPOINT_PATH=/path/to/rlinf-pi05-libero-130-fullshot-sft

SAM3 Configuration
------------------

SAM 3.0 segmentation is enabled for every LIBERO run. Download ``sam3.pt``
from `Hugging Face: facebook/sam3 <https://huggingface.co/facebook/sam3>`_
or `ModelScope: facebook/sam3 <https://modelscope.cn/models/facebook/sam3>`_,
then point at it via ``SAM3_CHECKPOINT_PATH``:

.. code-block:: bash

   # Hugging Face (request access on the model page first)
   hf auth login
   hf download facebook/sam3 sam3.pt --local-dir /path/to/sam3

   # ModelScope (use this instead of the Hugging Face commands above)
   modelscope download --model facebook/sam3 sam3.pt --local_dir /path/to/sam3

   export SAM3_CHECKPOINT_PATH=/path/to/sam3/sam3.pt

.. _minimal-command:

Run a Task
----------

Complete the model setup above and configure a planner with :doc:`../guides/configure_planner`. This command runs task 2 of ``libero_object_swap`` at seed 0:

.. code-block:: bash

   export PI05_CHECKPOINT_PATH=/path/to/rlinf-pi05-libero-130-fullshot-sft

   rpent --robot libero \
     --suite libero_object_swap --task 2 --seed 0 \
     --planner claude_code --model claude-opus-4-8

The suite selects the task family and, for perturbation suites, the perturbation type. To choose another suite, task, seed, or variant, see Task Selection below. To switch planners, see :doc:`../guides/configure_planner`.

View Results
------------

The terminal shows server startup, planner conversation, and tool calls. After the run, inspect ``episode.mp4``, ``transcript_*.json``, and ``run.log`` in the output directory; see :ref:`run-output-files` for default paths and step artifacts.

Inspect the final state with ``view_env_state(step=-1)``. Its top-level ``terminated`` value is the native success result; ``finish`` ends planning. See :doc:`../guides/dashboard` for live monitoring.

Dashboard
~~~~~~~~~

See :doc:`../guides/dashboard` to monitor runs, submit tasks, and stop a session.

Validation Status
~~~~~~~~~~~~~~~~~

- Verified (multiple runs): the v0.1 release tests and sampled paper
  reproduction cover LIBERO-PRO tasks; see the :doc:`release notes
  <../resources/release_v0.1>` for configurations, seeds, and episode counts,
  and the :doc:`leaderboard <../leaderboard/index>` for published scores.
- CPU only: offline unit tests cover task selection, tools, and result
  contracts.

Task Selection
--------------

A LIBERO run uses the following task settings:

.. list-table::
   :header-rows: 1

   * - Option
     - Meaning
   * - ``--suite``
     - Select a suite from :ref:`Core LIBERO-PRO suites <libero-pro-core-suites>`.
   * - ``--task``
     - Zero-based task index within the suite. Out-of-range indices and tasks with no stored initial states are rejected; invalid selections never substitute another task.
   * - ``--seed``
     - Environment seed; defaults to ``0``.
   * - ``--libero-type``
     - Installed LIBERO variant: ``standard`` | ``pro`` | ``plus``.

WAM Evaluation
--------------

A WAM backend predicts one chunk of actions per call, the environment executes
the chunk, and the next call observes the updated scene.

Prepare a worker with :doc:`../development/add_action_model` and keep the simulator
and SAM3 setup above. Pi0.5 weights are not needed for WAM. With Cosmos on port 8116:

.. code-block:: bash

   rpent --robot libero --suite libero_spatial --task 0 --seed 0 \
     --libero-type standard --am-backend cosmos-policy \
     --am-endpoint http://127.0.0.1:8116 --memory-profile local \
     --planner api --model <planner-model>

Fast-WAM uses ``--am-backend fast-wam`` and its worker endpoint. For LIBERO-PRO,
select a Pro suite and ``--libero-type pro`` in a Pro environment. WAM excludes
LIBERO-Plus, Flash and exploration. WAM uses a required local memory manager
and file tools, with a backend-specific directory that may be empty.
Use ``--memory-dir`` to select a compatible local corpus; HF memory is unsupported.
``wam_act(prompt=None, max_chunks=1)`` replaces the Pi0.5 tools and executes one
to four chunks with fresh observations. The worker's ``chunk_size`` metadata
declares the number of actions per chunk. A prompt override applies to
that call only. Chunk budgets do not specify where to stop inside a chunk.

.. _libero-pro:

.. _libero-pro-core-suites:

Tasks
-----

This table covers RPent's four core LIBERO-PRO task families and all of
their perturbation suites.

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - Family
     - Base suite
     - Perturbation suites
   * - Object
     - ``libero_object``
     - ``libero_object_task``, ``libero_object_swap``,
       ``libero_object_lan``, ``libero_object_object``
   * - Goal
     - ``libero_goal``
     - ``libero_goal_task``, ``libero_goal_swap``,
       ``libero_goal_lan``, ``libero_goal_object``
   * - Spatial
     - ``libero_spatial``
     - ``libero_spatial_task``, ``libero_spatial_swap``,
       ``libero_spatial_lan``, ``libero_spatial_object``
   * - LIBERO-10
     - ``libero_10``
     - ``libero_10_task``, ``libero_10_swap``, ``libero_10_lan``,
       ``libero_10_object``

Observation and Action
~~~~~~~~~~~~~~~~~~~~~~

The table distinguishes planner tools, model inputs, and the environment’s success criterion.

.. list-table::
   :header-rows: 1

   * - Item
     - Description
   * - Observation
     - RGB/depth camera views and end-effector/gripper state. Pi0.5 uses the scene and wrist images with robot state.
   * - Action
     - The planner calls Pi0.5 tools or motion primitives such as ``move_to`` and ``set_gripper``; these execute environment actions.
   * - Reward / success
     - Evaluate success using the final state’s top-level ``terminated`` value. A step limit or planner ``finish`` is not a success label.
   * - Task prompt
     - The task language comes from the selected suite/task and the current environment.

.. _libero-observation-action:



.. _libero-exploration:

.. _exploration-and-memory:

Task Memory
-----------

The HF memory workflow in this section applies to VLA; WAM uses local memory as
described above.

Evaluation is single-attempt and reads memory without updating it. The default
``hf`` profile uses ``--memory-version auto`` to select memory by model. See
:doc:`../guides/memory` for explicit versions, offline preparation, and the
versioned layout.

Exploration Mode
~~~~~~~~~~~~~~~~

Use ``--explore`` to build local memory or ``--memory-profile local`` to read a prepared corpus. See :doc:`../guides/memory` for the complete LIBERO workflow and commands. LIBERO’s native success result determines whether successful task records are published.

.. raw:: html

   <span id="reproducing-results"></span>

Experiment Reproduction
-----------------------

The :doc:`leaderboard <../leaderboard/performance>` records the published
LIBERO-PRO results. One row is a derived ``GPT-5.5 (xhigh)`` aggregate that
combines the six paper suites with two Long suites re-run on the
`reproduce/libero <https://github.com/RLinf/RPent/tree/reproduce/libero>`_
branch using ``gpt-5.5`` and ``xhigh`` reasoning. Use that row for suite-level
rates and the leaderboard's :doc:`evaluation protocol <../leaderboard/methodology>`
for the aggregation rule.

The command below reproduces one episode of ``libero_10_task``: task 0 at seed
0. Reproducing the published row requires the full task and seed matrix across
all eight suites. Complete this page's resource setup and start the services
described in :doc:`../guides/advanced_deployment` first.

.. code-block:: bash

   rpent --robot libero \
     --suite libero_10_task --task 0 --seed 0 \
     --planner codex \
     --model gpt-5.5 --reasoning-effort xhigh \
     --max-turns 100 \
     --planner-timeout-s 5000 \
     --max-episode-steps 10000 \
     --libero-type pro \
     --am-endpoint http://127.0.0.1:8220 \
     --sam3-endpoint http://127.0.0.1:8114

Tools the Planner Can Call
--------------------------

LIBERO tools fall into two groups: physical action tools and read-only tools.

**Physical action tools:**

- ``pi0_pick(prompt, ...)`` — use Pi0.5 to predict and execute a grasp.
- ``pi0_doubled(prompt, ...)`` — use Pi0.5 for a non-pick contact action.
- ``move_to(xyz, ...)`` — move the end effector to a world-frame position.
- ``move_pose(xyz, target_pitch=..., target_yaw=..., ...)`` — move position
  and orientation together.
- ``rotate_wrist(target_yaw=... / delta_yaw=..., ...)`` — rotate wrist yaw
  to an absolute target or by a relative amount.
- ``rotate_pitch(target_pitch=... / delta_pitch=..., ...)`` — tilt the
  gripper to an absolute pitch or by a relative amount.
- ``set_gripper(gripper=..., steps=...)`` — hold the pose and drive the
  gripper for a fixed number of steps.
- ``release(...)`` — open the gripper.

Physical action tools advance the environment and record new state and images.

**Read-only tools:**

- ``back_project(row, col, ...)`` — back-project an image pixel to world
  coordinates.
- ``segment(prompt=... / point=..., ...)`` — use SAM3 to segment an existing
  image with a text or point prompt.
- ``view_env_state(step=-1)`` — read a recorded state and its embedded
  observation images. Step ``0`` is initial; ``-1`` is latest.
- ``view_camera_meta(camera=..., step=-1)`` — read camera metadata for a
  recorded step. Step ``-1`` is latest.
- ``finish(status, summary)`` — end the current run.

These tools do not advance the environment.

What Runs Where
~~~~~~~~~~~~~~~

LIBERO separates simulation and model inference into services. The toolkit
uses their clients to execute the planner's requests.

- **env_server** (``robots/libero/env_server.py``) — owns the LIBERO
  MuJoCo env and EGL rendering. Exposes ``reset``, ``step``,
  ``chunk_step``, ``render_camera``, ``get_camera_meta``, … over an RPC
  transport (HTTP by default; socket via ``--transport socket``).
- **vla_server** (``rpent/robots/components/pi05_vla_server.py``) — owns the Pi0.5
  weights. Exposes ``predict`` over the same RPC transport (HTTP or
  socket).
- **sam3_server** (``rpent/robots/components/sam3_server.py``) — loads SAM 3.0 and
  segments a target region from a text description or one pixel on the target
  object. If the model produces multiple candidates, it selects the one with
  the highest model score and returns its mask as a compressed PNG through the
  same RPC transports (HTTP or socket).
- **toolkit** (``robots/libero/toolkit.py``) — defines the tools the
  LLM can call: ``pi0_pick`` (fed to Pi0.5), ``move_to``,
  ``rotate_wrist``, ``back_project``, ``view_env_state``,
  ``finish``, …

Bringing Your Own VLA
~~~~~~~~~~~~~~~~~~~~~

If you have a LIBERO-compatible VLA that is not Pi0.5, swap the model
client without touching the robot by:

1. Writing a new ``vla_server.py`` that exposes the same ``predict``
   RPC contract (over HTTP or socket).
2. Pointing at it with ``--am-endpoint [protocol://]host:port``.
3. Optionally updating ``robots/libero/toolkit.py`` if the tool
   surface (e.g. ``pi0_pick`` → ``mymodel_pick``) needs to change.

See :doc:`../development/add_primitive` for the full walkthrough.
