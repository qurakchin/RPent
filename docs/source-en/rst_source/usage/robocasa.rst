RoboCasa
========

`RoboCasa <https://robocasa.ai>`_ is the kitchen-scale, long-horizon
manipulation environment. In RPent it is driven by the **RLDX-1** VLA
policy, served over HTTP RPC by default (matching LIBERO); a
pickle-framed socket transport is also supported. See
``robots/robocasa/vla_server.py`` and ``robots/robocasa/__init__.py``
for the wire/transport selection.

Task families
-------------

RoboCasa covers the standard kitchen benchmarks:

- ``PickPlace*`` — pick objects from a source, place them at a target
  (counter to cabinet, sink to counter, and so on).
- ``Open*`` and ``Close*`` — open and close cabinet doors, drawers, and
  appliances.
- ``TurnOn*`` and ``TurnOff*`` — operate stove burners, microwave
  buttons, kettle switches, and similar toggles.

The exact catalog depends on the RoboCasa release; see the
`RoboCasa <https://robocasa.ai>`_ upstream for the current list.

Running a task
--------------

The RoboCasa CLI flags are registered by ``robots/robocasa/__init__`` and
are visible under ``rpent --env robocasa --help``:

.. code-block:: bash

   rpent --env robocasa \
         --robocasa-env OpenDrawer \
         --robocasa-split target \
         --seed 0 \
         --vla-model-path /path/to/rldx \
         --planner claude_code \
         --model claude-opus-4-8

Use ``--env-endpoint`` / ``--vla-endpoint`` to point at already-running
servers (``[protocol://]host:port``); when omitted, RPent spawns the env
and VLA daemons in-process and writes their logs to
``<output_dir>/env_server.log`` and ``<output_dir>/vla_server.log``.

Toolkit design vs. LIBERO
-------------------------

The RoboCasa toolkit exposes the same *shape* of tools as LIBERO (a
primitive call, a state view, a ``finish``), with two RoboCasa-specific
aspects:

- **Env-side helpers.** Grasp checks and action assembly need the live
  simulator env, so they live in ``env_server`` as RPCs. The agent-side
  skill holds **both** clients: the env client for render/step, the
  model client for RLDX-1 inference. See
  :doc:`../development/add_robot` for the rationale.
- **Observation shape.** RLDX-1 sees 3 camera video tensors
  ``(1, T, H, W, 3)`` stacked over history ``T``, plus ``state.*``
  fields, an annotation, and a session id used by ``reset_session`` /
  ``predict``.
