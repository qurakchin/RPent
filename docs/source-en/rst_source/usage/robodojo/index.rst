RoboDojo
========

RoboDojo is a pluggable simulation backend for RPent (``rpent --env robodojo``)
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
* The Pi0.5 policy is served by the shared
  ``rpent/robots/components/pi05_vla_server.py`` /
  ``pi05_vla_client.py`` (``--embodiment robodojo``); the RoboDojo-to-openpi
  view encoding lives in the client's ``_encode_obs_robodojo`` and the 14-D
  joint action decode in ``pi0_pick`` (``tools.py``).
* ``robots/robodojo/toolkit.py`` / ``tools.py`` — primitives:
  ``view_env_state``, ``back_project``, ``segment``, ``move_to``,
  ``set_gripper``, ``pi0_pick``, ``stabilize``, ``place_in_bin``,
  ``get_reward_details``, etc.
* ``robots/robodojo/robot_spec.py`` — ``RobotSpec`` factory (CLI, run config,
  runtime orchestration).
* ``robots/robodojo/tasks.py`` — dynamic mapping of all 54 RoboDojo tasks.

Quick start
-----------

.. code-block:: bash

   cd <rpent checkout>
   export PATH="$PWD/.venv/bin:$PATH" \
     SAM3_CHECKPOINT_PATH=$PWD/checkpoints/sam3/sam3.pt \
     HF_HUB_DISABLE_XET=1 CELL_TIMEOUT_S=3600
   rpent --env robodojo --task put_bottles_into_dustbin --layout 1 \
     --sim-device 0 --planner codex --model deepseek-v4-flash --max-turns 30

Output (reward-details audit, three-camera mp4s, transcript) is written to
``logs/<timestamp>_robodojo_<task>_l<layout>/``.

See :doc:`installation` for a from-scratch setup, :doc:`ab_protocol` for the
bare-policy vs harness A/B protocol, and :doc:`integration_log` for the full
integration record.
