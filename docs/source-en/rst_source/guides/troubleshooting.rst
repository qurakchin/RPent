Troubleshooting
===============

Start with the first error in ``run.log``; later messages usually follow from
it. Service startup failures are written to the ``*_server.log`` files in the
run's output directory, and planner messages are in ``transcript_*.json``.

Common Problems
---------------

.. list-table::
   :header-rows: 1
   :widths: 28 44 28

   * - Symptom
     - Check
     - Details
   * - ``rpent: command not found``
     - Activate the environment that installed RPent, for example
       ``source .venv/bin/activate``.
     - :doc:`../get_started/quickstart`
   * - Import error for a simulator or model at startup
     - Install the matching extra (``.[libero]``, ``.[libero-pro]``,
       ``.[robocasa]``, …). Install only one LIBERO variant per environment.
     - :doc:`../simulators/index`
   * - CUDA or driver error when a service starts
     - Use the PyTorch build that matches the driver, then rerun the
       environment's check command.
     - :doc:`../simulators/libero`,
       :doc:`../simulators/robocasa`
   * - Out-of-memory error
     - Check other processes on the GPU. Where supported, assign separate
       devices with ``--env-cuda-device`` and ``--am-cuda-device``.
     - :doc:`../simulators/robotwin`
   * - A service exits before the first tool call
     - Read ``env_server.log``, ``vla_server.log``, or ``sam3_server.log`` in
       the output directory; they record the failing component.
     - :ref:`run-output-files`
   * - Model or asset download fails
     - For gated weights, request access and run ``hf auth login``. Set
       ``HF_ENDPOINT`` for a mirror, or use the ModelScope command when the
       page provides one.
     - :doc:`../get_started/quickstart`
   * - Planner check fails
     - Run ``rpent-check-llm`` with the same ``--planner`` and ``--model``; its
       error class separates configuration, authentication, model, and network
       failures.
     - :ref:`planner-check`
   * - The planner connects but every task fails
     - Verify the checkpoint paths and the native success signal; inspect the
       recorded video and final state before changing planner settings.
     - :ref:`leaderboard-protocol`
   * - External service is unreachable
     - Pass ``host:port`` endpoints, not a bare port. Keep the service running
       in another terminal or node.
     - :doc:`advanced_deployment`
   * - Memory cache is rejected
     - Remove extra files from the versioned cache, or let an online sync
       rebuild it. ``HF_HUB_OFFLINE=1`` requires a complete, unmodified cache.
     - :doc:`memory`
   * - Flash cannot find a plan
     - The task may have no successful source plan, and Astra memory has no
       replay assets. Use GPT-5.5 memory for Flash.
     - :doc:`flash`
   * - Dashboard does not open from another machine
     - The default bind address is ``127.0.0.1``; use SSH port forwarding.
     - :doc:`advanced_deployment`
   * - A real-robot run refuses to start
     - Check the robot's calibration and pose prerequisites on its page; the
       environment service validates poses before starting.
     - :doc:`../real_world_robots/index`

Collecting Evidence
-------------------

For a bug report, include the command, the first error from ``run.log``, the
relevant service log, and the output directory layout. Do not include API keys
or credentials. A failed task is not automatically a framework bug: compare the
final environment state with the success criterion on the environment page.
