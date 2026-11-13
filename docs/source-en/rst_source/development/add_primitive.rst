Add an Action Primitive
=======================

An *action primitive* in RPent turns a tool call into an action that
the environment can execute. It can be a learned policy (a VLA, a WAM,
a diffusion planner) or a scripted routine (``move_to``,
``open_gripper``). Model-based primitives run in a model service and are called
through a model client; scripted primitives run in the agent process. Both
expose the same tool schema. This page covers declaration, registration, and
execution.

.. page-head::
   :for: Developers exposing a new action or perception capability as a tool
   :outcome: You can declare, register, and validate a scripted or model-backed primitive
   :read-when: You are adding a tool the planner can call
   :skip-when: You need to add the model service itself; see :doc:`add_action_model`

**Page map:** when to add one → prerequisites → scripted primitive →
model-backed tools → runtime wiring → test → design principles → primitive
families → troubleshooting and next steps.

When to add a primitive
-----------------------

Add a primitive when the planner needs a new action or observation that no
existing tool exposes. Rename or wrap an existing tool if its behavior already
matches; a new primitive is a new tool schema the model will see, so keep the
set small and the names intent-level.

Prerequisites
-------------

- A working robot package with a toolkit; follow :doc:`add_robot` if the
  package does not exist yet.
- The environment client methods the primitive will call (``step``,
  ``chunk_step``, ``get_obs``, or a custom RPC).
- The test extra (``pip install -e ".[test]"``) for the offline tool tests.

Add a scripted primitive
------------------------

Declare the method on the robot's primitives class and register its bound tool:

.. code-block:: python

   from rpent.tools import ToolResult, iter_tools, tool

   class MyRobotPrimitives:
       @tool
       def open_drawer(self, dx: float = 0.15) -> ToolResult:
           """Pull the grasped drawer handle backwards.

           Args:
               dx: Pull distance in meters.
           """
           self._env.step(build_open_drawer_chunk(dx))
           return ToolResult(data={"ok": True, "dx": dx})

   # In the toolkit, after constructing self._primitives:
   self.add_tools(iter_tools(self._primitives))

Type annotations and the docstring define the model-facing schema. Toolkit
validates arguments and captures state through ``get_env_state`` after
execution. Use ``@tool(readonly=True)`` for readers such as ``view_env_state``
and ``back_project``. For module-level tools, exclude internal resources with
``@tool(exclude=("state",))`` and bind them with ``Tool.with_handler``.
All three planners use the registered declarations.

.. _add-primitive-model-based:

Model-backed tools
------------------

For VLA/WAM services, clients, adapters and session lifecycle, follow
:doc:`add_action_model`. The platform tool calls its model client, executes the
returned native action chunk through the environment, and returns a
``ToolResult``. Register it with the same ``@tool`` and ``iter_tools``
mechanism used above.

Runtime wiring: single-threaded serve (EGL-rendering backends)
--------------------------------------------------------------

Most backends use the ``serve`` inherited from their base class, which spawns a
worker thread per request. If your server process renders with EGL (e.g.
robosuite / MuJoCo offscreen rendering, see ``render_camera``), the EGL context
must stay on one thread. Concurrent dispatch would break that affinity.

Mix :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin` into your
facade class (**before** ``BaseEnvFacade`` / ``BaseVLAFacade``) and inherit the
``serve`` it overrides. That ``serve`` runs the transport server on a daemon
thread. Every dispatch still executes serially on the thread that called
``serve``, normally the process main thread. Requests pass from the transport
thread through a work queue:

.. code-block:: python

   from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin
   from rpent.robots.components.env_facade_base import BaseEnvFacade

   class MyEnvFacade(MainThreadServeMixin, BaseEnvFacade):
       ...

   facade.serve(transport="http", host=host, port=port)  # dispatch on the main thread

The overridden ``serve`` keeps the same contract as
:class:`~rpent.utils.rpc.RpcFacade`'s ``serve``: it still supports
``healthz`` / ``shutdown``, parent-watch, and sessions (when constructed with
``enable_sessions=True``, ``serve`` still requires ``session_sweep_s``).
Subclasses do **not** need to override ``serve`` to delegate — just inherit it
(see ``RoboCasaEnvFacade`` in ``robots/robocasa/env_server.py``). Backends that
do not need EGL single-threading keep the plain inherited ``serve``.

Test
----

Add an offline test that builds the toolkit, lists the tool schema, and calls
the new primitive against a stub environment. Reuse
``tests/unit_tests/rpent/tools/test_tool_schema_contracts.py`` and the platform
tests under ``tests/unit_tests/robots/<robot>/``. A model-backed primitive needs
the model service or a stubbed client; task success still needs an integration
run on the target environment.

Design principles for a new primitive
-------------------------------------

- **Tools describe intent, not motion.** A good tool name is ``pi0_pick``, not
  ``execute_action_chunk_of_length_20``.
- **Stateful tools capture state before returning to the planner.** Toolkit
  calls ``get_env_state`` after the handler while retaining exclusive execution.
  ``readonly`` tools skip this capture and may run alongside other readonly
  tools.
- **Keep result data small.** Tool return values are fed back to the LLM as
  text. Save larger observations through ``EnvState.save``; ``EnvState``
  automatically records each logical base name in its owned
  ``StepRecord.artifacts`` set. Expose images through ``view_env_state`` and
  geometry through environment tools rather than returning raw paths.
- **Guardrails belong in env_server**, not in the toolkit. The LLM can and will
  call any tool with any arguments; workspace bounds and safety clamps must be
  enforced on the server side.

Primitive families
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Family
     - Execution location
     - Examples
   * - **Model-based**
       (VLA / WAM / diffusion / …)
     - Runs in its own model service process and is called through
       a *model client* held by the toolkit.
     - Pi0.5 (LIBERO), RLDX-1 (RoboCasa)
   * - **Scripted**
       (kinematic / heuristic)
     - Runs in the agent process, with an optional server-side RPC for
       kinematics. It does not load model weights.
     - ``move_to``, ``rotate_wrist``, ``release``,
       ``back_project``

From the LLM's perspective, both types expose the same interface: a tool
schema, a primitives method, and a state dump after the call. They differ only
in how the method is implemented.

Troubleshooting and next steps
------------------------------

- **The tool is missing from ``list_tools()``.** Check that the bound method is
  registered with ``add_tools`` or ``add_tool`` after the primitives object
  exists.
- **Arguments are rejected.** The schema comes from the signature and
  docstring; keep type annotations and the Google-style ``Args`` section in
  sync with the handler.
- **State is stale after the call.** Confirm the tool is not marked
  ``readonly`` and that the environment advanced before the handler returned.
- **EGL rendering fails under concurrent calls.** Use the single-threaded
  ``serve`` above instead of the default dispatch.

Next: connect a model service in :doc:`add_action_model`, or review the tool
contract in :doc:`../development/interfaces`.
