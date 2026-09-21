RoboDojo
========

RoboDojo is a pluggable simulation backend for RPent (``rpent --robot robodojo``)
that brings Isaac Sim / IsaacLab (dual ARX-X5 arms, Pi_05 policy) into the
RPent LLM-in-the-loop runner, alongside the existing LIBERO / RoboCasa /
RoboTwin backends. The planner (LLM), toolkit protocol, SAM3 perception, and
memory layers are reused unchanged; only the "body" (simulator/robot) is
swapped.

Key modules
-----------

* ``robots/robodojo/env_server.py`` — Isaac Sim RPC server (main-thread
  rendering; head + dual-wrist RGB-D with intrinsics/extrinsics; joint/ee
  actions; per-camera video recording).
* ``robots/robodojo/env_client.py`` — rpent-side client inheriting
  ``BaseEnvClient``.
* The Pi0.5 policy is served by the shared, env-agnostic
  ``rpent/robots/components/pi05_vla_server.py`` and its client
  ``rpent/robots/components/pi05_vla_client.py``. RoboDojo selects the
  ``robodojo`` embodiment (``--embodiment robodojo``), which the server maps
  to the ``pi05_robodojo_arx_x5`` openpi config and the client to
  ``_encode_obs_robodojo`` (head + two wrist views, 14-D joint state). The
  server reads its weights from ``--model-path`` / ``PI05_CHECKPOINT_PATH``
  and its normalisation statistics from ``--norm-stats-path`` /
  ``PI05_NORM_STATS_PATH``. The 14-D joint action decode lives in
  ``pi0_pick`` (``tools.py``). There is no RoboDojo-local
  ``vla_server.py`` / ``vla_client.py``.
* ``robots/robodojo/toolkit.py`` / ``tools.py`` — primitives:
  ``view_env_state``, ``back_project``, ``segment``, ``move_to``,
  ``set_gripper``, ``pi0_pick``, ``stabilize``, ``place_in_bin``,
  ``get_reward_details``, etc.
* ``robots/robodojo/robot_spec.py`` — ``RobotSpec`` factory (CLI, run config,
  runtime orchestration).
* ``robots/robodojo/tasks.py`` — read-only task inventory. It globs the
  ``*.yml`` task-config filenames under the workspace's
  ``task/RoboDojo/config/`` directory (excluding ``_task.yml``) instead of
  embedding a fixed task list, so the available tasks track the RoboDojo
  checkout.

Quick start
-----------

.. code-block:: bash

   cd <rpent checkout>
   export PATH="<venv>/bin:$PATH" \
     ROBODOJO_WORKSPACE=<workspace> \
     PI05_CHECKPOINT_PATH=<converted Pi0.5 checkpoint> \
     PI05_NORM_STATS_PATH=<dir containing norm_stats.json> \
     SAM3_CHECKPOINT_PATH=$PWD/checkpoints/sam3/sam3.pt \
     HF_HUB_DISABLE_XET=1 CELL_TIMEOUT_S=3600
   rpent --robot robodojo --task put_bottles_into_dustbin --layout 1 \
     --cuda-device 0 --planner codex --model deepseek-v4-flash --max-turns 30

``--cuda-device`` (not ``--sim-device``) selects the GPU for the Isaac Sim env
server and the Pi0.5 VLA server. ``--env robodojo`` is a deprecated alias for
``--robot robodojo``.

Output (reward-details audit, three-camera mp4s, transcript) is written to
``logs/<timestamp>_robodojo_<task>_l<layout>/``.

See :doc:`installation` for a from-scratch setup, ``docs/ROBODOJO_INSTALLATION.md``
for the command-complete three-runtime guide (editable IsaacLab, CuRobo, the
JAX-to-PyTorch checkpoint conversion, and required env vars),
:doc:`ab_protocol` for the bare-policy vs harness A/B protocol, and
:doc:`integration_log` for the full integration record.
