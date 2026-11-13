Add a Robot or Simulator
========================

This guide walks through what you need to write to plug a new physical /
simulated robot into RPent's LLM-in-the-loop runner. Use
``robots/libero/`` as the worked reference.

**Page map:** integration rules → steps 1–6 → conventions → tests.

Integration Guidelines
----------------------

- **Reuse RPent abstractions.** Prefer existing Env, VLA, runtime, and memory
  components such as ``BaseEnvClient``, ``BaseEnvFacade``,
  ``BaseVLAClient``, ``BaseVLAFacade``, and ``MemoryManager``.
- **Prefer RLinf Env or VLA implementations.** If RLinf already supports the
  required Env or VLA, keep RPent as a thin adapter where possible.
- **Stay consistent with existing robot integrations where possible.**
  Follow the existing ``RobotSpec``, Prompt, Toolkit, and runtime patterns
  instead of introducing a new shared mechanism for one robot.
- **Explain when reuse is not possible.** If an existing RPent or RLinf
  Env / VLA cannot be reused, explain why in the PR description or open an
  issue so the existing abstraction can be improved.

Integration Steps
-----------------

For the overall process layout, service responsibilities, and communication
model, see :doc:`System Design <architecture>`. This guide focuses on the
extension points required to add a robot. Complete them in the following
order:

1. Register the ``RobotSpec`` and toolkit factory in the
   :ref:`entry point <add-robot-entry>`.
2. Implement :ref:`env_client and env_server <add-robot-env-rpc>`. To
   integrate a VLA service and model client, see :ref:`Add a VLA (or other
   model-based primitive) <add-primitive-model-based>`.
3. :ref:`Define the prompts <add-robot-prompts>`.
4. :ref:`Implement the toolkit and primitives <add-robot-toolkit>`.
5. :ref:`Register robot arguments and build RunConfig
   <add-robot-config>`.
6. Implement the :ref:`runtime hook <add-robot-runtime>`. The same hook starts
   the complete runtime for normal CLI runs or a selected component subset for
   the Dashboard.
7. Add :ref:`tests for the environment, its components, and the complete
   policy chain <add-robot-testing>`.

.. _add-robot-entry:

Entry Point
-----------

For a new robot named ``myrobot``, use the following directory layout:

.. code-block:: text

   robots/myrobot/
       __init__.py            # package entry point; re-exports the factories
       robot_spec.py          # RobotSpec, factories, Dashboard spec, runtime hooks
       env_client.py          # MyEnvClient — agent-side RPC stub (§1)
       prompt_bundle.py       # system()/user() prompt factories         (§2)
       toolkit.py             # MyRobotToolkit + primitives + tool definitions (§3)
       env_server.py          # server-side facade + RPC server (§1)
       vla_server.py          # (optional) VLA model server

``__init__.py`` is the robot package's entry point. Keep it small and
re-export the factories implemented in ``robot_spec.py``. The registry in
``rpent/robots/base.py`` lazily imports ``robots.<name>`` on demand and calls
these two functions:

.. code-block:: python

   # robots/myrobot/__init__.py
   from robots.myrobot.robot_spec import get_robot_spec, get_toolkit

   # robots/myrobot/robot_spec.py
   from rpent.dashboard.events import DashboardEventSink
   from rpent.memory import MemoryManager
   from rpent.robots.robot_spec import RobotSpec, RunConfig
   from rpent.robots.prompt_bundle import PromptBundle
   from rpent.utils.config import get_memory_dir
   from robots.myrobot.prompt_bundle import system_prompt, user_prompt

   MYROBOT_DASHBOARD_SPEC = {...}

   def get_robot_spec() -> RobotSpec:
       return RobotSpec(
           name="myrobot",
           prompts=PromptBundle(system=system_prompt, user=user_prompt),
           add_cli_args=_add_cli_args,
           parse_config=_parse_config,
           init_runtime=_init_runtime,
           resolve_dashboard=lambda args: MYROBOT_DASHBOARD_SPEC,
       )

   def get_toolkit(
       *,
       runtime_kwargs,
       dashboard_events: DashboardEventSink,
       config: RunConfig,
   ):
       from robots.myrobot.toolkit import MyRobotToolkit
       return MyRobotToolkit(
           runtime_kwargs=runtime_kwargs,
           dashboard_events=dashboard_events,
           memory=MemoryManager(
               root=config.prompt_vars.get("memory_dir") or get_memory_dir("myrobot"),
           ),
       )

   def _add_cli_args(parser, use_dashboard) -> None:
       """Register robot flags on the shared parser. See §4."""
       ...

   def _parse_config(args) -> RunConfig:
       """Validate final `args`, return a RunConfig. See §4."""
       ...

   def _init_runtime(
       args,
       output_dir,
       dashboard_events: DashboardEventSink,
       components: set[str] | None,
   ):
       """Initialize all runtime components, or only the selected subset.

       Returns (daemons, runtime_kwargs). See §5.
       """
       ...

``resolve_dashboard`` is an optional callback. Leave it as ``None`` if the
environment does not support Dashboard control. Otherwise, return a spec defined
in the robot package: its ``task`` section describes the command, validated fields, display
template, and output slug; robot-specific Session settings remain normal CLI
arguments; ``runtime_components`` describes service rows;
and ``primitives`` is the ordered allowlist of Toolkit actions displayed and
executable as Dashboard controls. Camera tabs are discovered from the PNG
artifacts in each recorded step. Keep task suggestions in the spec so
importing the robot does not require simulator packages. See
``robots/libero/robot_spec.py`` for the reference shape.

The callback receives the parsed session arguments, so it can select components
based on options such as ``--am-backend``. For a fixed layout, return the static
spec as in the example above. Physical environment checks and Dashboard startup
both call ``resolve_dashboard(args)``.

That's the entire registration step — ``_resolve_robot(name)`` does an
``importlib.import_module(f"robots.{name}")``, so dropping the package under
``robots/`` on disk is enough. No central list to update.

The sections below describe what each referenced module must contain.
``_add_cli_args`` / ``_parse_config`` are covered in §4 and the runtime hook
in §5.

.. _add-robot-env-rpc:

1. ``env_client.py`` + ``env_server.py``
-----------------------------------------

These files connect the agent process to ``env_server``. The client converts
method calls into RPC requests, and ``env_server`` handles those requests.

1.1 Env Client (agent Side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subclass :class:`rpent.robots.components.env_client_base.BaseEnvClient`. It already
validates ``env.get_env_meta`` at startup, performs the initial reset, caches
``last_obs``, and implements the common ``reset``, ``step``, ``chunk_step``,
``render_camera``, ``get_camera_meta``, and ``get_task_language`` RPCs.
Add only environment-specific methods, and extend the timeout table when an
extension needs its own timeout. Keep RPC names stable — the server-side
facade registers each name explicitly.

.. code-block:: python

   from rpent.robots.components.env_client_base import BaseEnvClient

   class MyEnvClient(BaseEnvClient):
       _TIMEOUT_S = {
           **BaseEnvClient._TIMEOUT_S,
           "env.custom_method": 30.0,
       }

       def custom_method(self, arg):
           return self._client.call(
               "env.custom_method",
               args=(arg,),
               timeout_s=self._TIMEOUT_S["env.custom_method"],
           )

   env = MyEnvClient(rpc_client, expected_meta=expected_meta)

1.2 Env Server (server Side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Mirror the client's API in a facade class on the server side (e.g.
``MyEnvFacade``). Subclass
:class:`rpent.robots.components.env_facade_base.BaseEnvFacade`; it provides the common RPC
routes and read/write dispatch locking. Implement the common environment
methods and extend ``_register_rpc`` for environment-specific routes. Methods
take the same positional / keyword arguments the client sends and return
transport-supported Python / NumPy values (not torch — the agent side does not
import torch).

.. code-block:: python

   from rpent.robots.components.env_facade_base import BaseEnvFacade

   class MyEnvFacade(BaseEnvFacade):
       def __init__(self, env, meta):
           self._env = env
           self._meta = meta
           super().__init__()

       def _register_rpc(self):
           super()._register_rpc()
           # Custom methods must be registered explicitly
           self._rpc["env.custom_method"] = self.custom_method

       # Abstract methods required by BaseEnvFacade
       def get_env_meta(self): ...
       def reset(self): ...
       def step(self, action): ...
       def chunk_step(self, actions, **kwargs): ...
       def get_camera_meta(self, camera_name, **kwargs): ...
       def render_camera(self, camera_name, **kwargs): ...
       def get_task_language(self): ...

       def custom_method(self, arg): ...

   facade = MyEnvFacade(env, meta)
   facade.serve(transport="http", host=host, port=port)

``BaseEnvFacade`` registers common routes through ``_register_rpc`` and
serializes state-changing calls with its read/write lock. Add a route to
``_readonly_methods`` only when it is genuinely safe to run concurrently with
other reads. The inherited ``RpcFacade.serve`` handles transport binding (HTTP
or socket), ``healthz`` / ``shutdown``, parent-death detection, and clean
teardown.

.. _add-robot-prompts:

2. ``prompt_bundle.py``
-----------------------

Define two prompt factories, ``system_prompt(variables)`` and
``user_prompt(variables)``, and build a ``PromptBundle(system=system_prompt,
user=user_prompt)`` in the robot's ``robot_spec.py`` (see the entry point
above). Each factory receives the run's prompt variables and returns a
``PromptNode``, typically an ordered ``dict[str, PromptNode]`` of titled
sections; ``PromptBundle.render`` assembles and fills them. One prompt serves
every planner (API loop, Claude Code, Codex):
refer to tools by their bare names (``move_to``, ...) and note once that the
Claude Code and Codex SDKs show them as ``mcp__rpent__<name>``. Do not
maintain separate prompt copies for CLI and API planners.

.. code-block:: python

   # robots/myrobot/prompt_bundle.py
   from typing import Mapping

   from robots.myrobot.prompts import system as system_parts
   from robots.myrobot.prompts import user as user_parts
   from rpent.prompt.utils import PromptNode

   def system_prompt(
       variables: Mapping[str, object] | None = None,
   ) -> PromptNode:
       return {
           "INTRO": system_parts.PREAMBLE,
           "GOAL": system_parts.GOAL,
           "RULES": system_parts.RULES,
           "WORKFLOW": system_parts.WORKFLOW,
           "ENVIRONMENT": system_parts.ENVIRONMENT,
           "OUTPUT": system_parts.OUTPUT,
       }

   def user_prompt(
       variables: Mapping[str, object] | None = None,
   ) -> PromptNode:
       return {
           "TASK": user_parts.TASK,
           "BEGIN": user_parts.BEGIN,
       }

Keep the prompt content under the robot package, for example in
``robots/myrobot/prompts/system.py`` and ``user.py``. Section bodies are plain
strings (or ``BulletList`` / ``Numbered``) with ``{{suite}}`` / ``{{task}}`` /
``{{seed}}`` / ``{{output_dir}}`` / ``{{recipe_tag}}`` placeholders filled at
render time.

.. _add-robot-toolkit:

3. ``toolkit.py``
------------------

This module owns the tool schemas, primitives, per-step state records, and
the list of tools available through MCP. LIBERO splits these between
``tools.py`` and ``toolkit.py``; a new robot may keep them in one
``toolkit.py`` module.

A toolkit module typically contains four pieces:

**Primitives class** (e.g. ``MyRobotPrimitives``) — a Python object owned
by the toolkit. It holds the ``EnvClient``, the VLA ``model`` client, and any
state needed for the current run. It exposes one method per primitive tool
(``move_to``, ``pi0_pick``, ``release``, …), with each method returning a
``ToolResult`` with log data and optional PNG images.

**Tool definitions and handlers** — functions and methods decorated with
``@tool``. Type annotations and Google-style docstrings define their schemas and
descriptions, including readers such as ``view_env_state`` and ``back_project``.

**Per-step state dump** — ``dump_state(primitives, env_state, log)`` opens
``env_state.record_step(...)`` and receives the allocated step index; the
``StepRecord`` is appended and committed immediately. Save large observations
through ``env_state.save(...)`` — inside a ``record_step`` block the ``step``
argument may be omitted (it defaults to the new step), pass an explicit
``step=<int>`` to target a different step, and ``step=None`` for run-level
artifacts. ``EnvState`` adds every successfully saved base name to the step's
flat ``artifacts`` set automatically. Readers use the canonical artifact
filenames rather than maintaining a parallel observation index.

**Toolkit class** — subclass ``rpent.tools.toolkit.Toolkit``:

- forward the required ``memory`` (a :class:`~rpent.memory.MemoryManager`) and ``state`` to
  ``super().__init__(...)``. Configure ``memory_access`` and
  ``inbox_cell_tag`` on the ``MemoryManager``; eval uses read-only access by
  default.
- build the primitives in ``__init__`` through a custom initialization
  helper (named ``init_primitives`` in LIBERO; it calls
  ``EnvState.reset()``, constructs the primitives, and dumps step 0),
- register bound tools with ``self.add_tools(iter_tools(self._primitives))``
  or ``self.add_tool(definition)``. Use ``definition.with_handler(...)`` to
  bind internal resources or execution guards; Toolkit captures post-action state,
- override ``close()`` to save remaining agent-side artifacts through
  ``EnvState`` (for example ``state.save("episode.mp4", frames, step=None)``).

``runtime_kwargs`` (forwarded from ``robot_spec.py:get_toolkit``) is the dict
the toolkit passes verbatim to your primitives' ``__init__`` — typically
``{"env": MyEnvClient(...), "model": VLAClient(...), ...}``.

Conventions Worth Keeping
-------------------------

- ``output_dir`` is the working directory that the runner creates for each
  run. Environment observations are owned by ``EnvState``; callers use logical
  base names and never construct storage paths. Transcripts and other
  run-management outputs share the same run directory.
- Tools expose ``name``, ``description``, and ``input_schema``. Each planner
  adapts registered tools to its model interface.
- Server-side return values must be picklable and torch-free.
- Each primitive tool dumps a fresh state snapshot after running so the next
  ``view_env_state`` call reflects the post-action world.
- Treat ``dump_state`` as the source of truth for what the agent sees — any new
  modality (e.g. tactile, force) goes through it.

.. _add-robot-testing:

6. Tests to Add
---------------

When adding a robot, test each runtime component it uses separately, then run
one complete policy chain. For example, a robot using Env, Pi0.5, and SAM3
needs an Env test, a Pi0.5 inference test, a SAM3 segmentation test, and a
policy-chain test. Each component test must make a real request and check the
result, beyond importing the module or checking server health.

Run offline tests with ``pytest tests/unit_tests/robots/myrobot -v``; after
preparing the robot's GPU resources, run ``pytest tests/e2e_tests/myrobot -v``.
Component coverage and the policy-chain checklist are in
:doc:`add_robot_reference`.
