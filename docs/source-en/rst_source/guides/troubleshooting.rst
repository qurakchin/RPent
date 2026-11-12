Troubleshooting
===============

Start with the first error in ``run.log``; later messages usually follow from
it. Service startup failures are written to the ``*_server.log`` files in the
run's output directory, and planner messages are in ``transcript_*.json``.

Common Problems
---------------

Each row gives a check, a command that fixes or confirms the cause, and the
step to repeat. Rerun with a new ``--output-dir`` so the failed run keeps its
logs and artifacts.

.. list-table::
   :header-rows: 1
   :widths: 18 22 45 15

   * - Symptom
     - Check
     - Fix and recovery
     - Details
   * - ``rpent: command not found``
     - The active Python environment does not contain RPent.
     - ``source .venv/bin/activate``, confirm with ``which rpent``, then rerun
       the original command.
     - :doc:`../get_started/quickstart`
   * - Import error for a simulator or model at startup
     - The matching extra is missing from this environment.
     - Install it, for example ``uv pip install -e ".[libero-pro]"``. Keep one
       LIBERO variant per environment, then rerun.
     - :doc:`../simulators/index`
   * - CUDA or driver error when a service starts
     - PyTorch does not match the driver or GPU.
     - Check with ``python -c "import torch; print(torch.version.cuda,
       torch.cuda.is_available())"``; reinstall the matching PyTorch wheel,
       then rerun.
     - :doc:`../simulators/libero`,
       :doc:`../simulators/robocasa`
   * - Out-of-memory error
     - Another process holds GPU memory, or both services share one device.
     - Check ``nvidia-smi``, stop other jobs, then split devices:
       ``--env-cuda-device 0 --am-cuda-device 1 --sam3-cuda-device 0``.
     - :doc:`cli`
   * - A service exits before the first tool call
     - The failing service recorded its error.
     - Read ``tail -n 50 <output-dir>/env_server.log`` (also
       ``vla_server.log`` and ``sam3_server.log``); fix the first error, then
       rerun with a new output directory.
     - :ref:`run-output-files`
   * - Model or asset download fails
     - Authentication, mirror, or disk space.
     - Run ``hf auth login`` for gated weights. For a mirror, prefix the
       download: ``HF_ENDPOINT=https://hf-mirror.com
       liberopro-download-assets --skip-existing``. Rerun the failed step;
       ``--skip-existing`` keeps completed files.
     - :doc:`../get_started/quickstart`
   * - Planner check fails
     - Configuration, authentication, model, or network error.
     - Rerun ``rpent-check-llm --planner claude_code --model
       claude-opus-4-8``; fix the reported class, then rerun the full task.
     - :ref:`planner-check`
   * - The planner connects but every task fails
     - Checkpoint paths or the native success signal.
     - Inspect ``view_env_state(step=-1)``; only the top-level ``terminated``
       value is success. Correct the checkpoint path, then rerun.
     - :ref:`leaderboard-protocol`
   * - External service is unreachable
     - Endpoint format or a stopped service.
     - Check the RPC endpoint with ``curl -s -X POST
       http://HOST:PORT/call -H 'Content-Type: application/json' -d
       '{"method":"healthz"}'``; it should return ``{"status": "ok"}``. Start
       or forward the service, then rerun.
     - :doc:`advanced_deployment`
   * - Memory cache is rejected
     - Extra files or an incomplete cache.
     - Remove the extra files, or rebuild online with ``python -m
       robots.libero.memory sync --memory-version GPT_6_astra_low``. With
       ``HF_HUB_OFFLINE=1`` the cache must be complete and unchanged.
     - :doc:`memory`
   * - Flash cannot find a plan
     - The selected memory has no successful source plan or replay assets.
     - Use ``--memory-version GPT_5.5_xhigh`` or a local ``--memory-dir`` that
       contains ``flash/`` assets, then rerun.
     - :doc:`flash`
   * - Dashboard does not open from another machine
     - The server binds ``127.0.0.1`` by default.
     - Forward the port printed at startup: ``ssh -N -L
       8000:127.0.0.1:8000 USER@HOST``, then open ``http://127.0.0.1:8000``.
     - :doc:`advanced_deployment`
   * - A real-robot run refuses to start
     - Calibration, pose prerequisites, or an emergency stop.
     - Complete the robot's calibration and pose check, release the emergency
       stop, and confirm the arm and gripper state before rerunning.
     - :doc:`../real_world_robots/index`

Collecting Evidence
-------------------

For a bug report, include the command, the first error from ``run.log``, the
relevant service log, and the output directory layout. Do not include API keys
or credentials. A failed task is not automatically a framework bug: compare the
final environment state with the success criterion on the environment page.
