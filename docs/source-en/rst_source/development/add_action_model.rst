Add an Action Model
===================

Integrate a VLA or WAM service and connect its predictions to a platform's
native action executor. Tool declarations and state capture are described in
:doc:`add_primitive`; platform discovery and runtime wiring are in :doc:`add_robot`.

.. page-head::
   :for: Developers integrating a VLA or WAM service
   :outcome: You can connect a model service to a platform's action executor and test the path
   :read-when: You are adding or replacing an action model
   :skip-when: You only need tool declarations; see :doc:`add_primitive`

**Page map:** when to add one → prerequisites → shared architecture → add a VLA
→ add a WAM → tests → troubleshooting and next steps.

When to add an action model
---------------------------

Add an action model when a platform has no client for the model you want to run,
or when the model's observation or action layout differs from the platform's
native controls. If the model and platform pair is already supported, deploy it
with the platform page's ``--am-backend`` and endpoint instead of writing a new
integration.

Prerequisites
-------------

- A platform client that exposes observations and executes native action chunks;
  see :doc:`add_robot`.
- The model's inference entry point and weights, or a running model service.
- The data layout of both sides: camera order, state vector, action dimension,
  and chunk length. Mismatches are resolved in the adapter, not in the platform
  client.

Shared Architecture
-------------------

RPent handles agent orchestration, platform observation/action mapping and
service connections. Model integrations reuse RLinf's loading, inference and
data transforms where it supports the required model and platform. For other
pairs, the model package connects the model's native implementation and supplies
the missing transforms.

VLA and WAM share AM base classes for RPC registration and prediction dispatch.
VLA retains its existing model-specific payloads and inference paths. WAM uses
the physical observation and native control declarations in ``am_contracts.py``
to connect platform clients to model adapters.

The WAM execution path illustrates the platform/model boundary:

.. code-block:: text

   CLI / Dashboard
     -> robots/<platform>/robot_spec.py: configuration and service startup
     -> toolkit.py: register platform tools
     -> wam_act: observe, predict, execute, record
     -> observation.py + wam_client.py: physical observations and control identity
     -> BaseWAMClient -> existing HTTP/socket RPC -> BaseWAMFacade
     -> <model>/adapter/encode.py -> predict_native -> adapter/decode.py
     -> action chunk -> platform env_client.chunk_step -> simulator

``wam_act`` lives in LIBERO's ``tools.py`` and RoboTwin's ``primitives.py``.
Both use ``@tool`` and return ``ToolResult(data=...)``. The existing platform
toolkit owns registration, cancellation, state capture and recording.

.. list-table:: Ownership
   :header-rows: 1

   * - Location
     - Responsibility
   * - ``robots/<platform>/observation.py``
     - Extract named physical sensors and state. No model normalization.
   * - ``robots/<platform>/control.py``
     - Define native action order, semantics and execution mode.
   * - ``robots/<platform>/wam_client.py``
     - Select a compatible controller and attach execution identity to observations.
   * - ``rpent/robots/components/am_contracts.py``
     - Declare shared physical observations/native control and WAM-specific capability, request and result dictionaries in separate sections.
   * - ``am_client_base.py``
     - Define the shared ``BaseAMClient`` and its VLA/WAM subclasses; share prediction dispatch and timeouts, keeping each contract's arguments and checks.
   * - ``am_facade_base.py``
     - Share prediction routes, optional model metadata and RPC session setup through ``BaseAMFacade``; keep VLA and WAM behavior in subclasses.
   * - ``am_runtime.py``
     - Register common deployment options, resolve VLA/WAM settings into ``AMConfig``, and start workers with their Python, working directory and GPU configuration.
   * - ``rpent/robots/components/pi05_vla_client.py``
     - Adapt platform observations and model outputs for Pi0.5; other VLA integrations provide their own model clients.
   * - ``<model>/runtime_config.py``
     - Supply WAM model-specific arguments, defaults and configuration requirements.
   * - ``<model>/server.py``
     - Load a WAM model or connect its native service, and implement the inference call.
   * - ``<model>/adapter/{__init__,encode,decode}.py``
     - Register paired transforms, build model input and restore native actions.

Physical observations are reusable by VLA and WAM integrations. Model encoders
remain distinct: Cosmos uses LIBERO's xyzw quaternion in a 9D state, whereas
Fast-WAM converts orientation to axis-angle for an 8D state. RoboTwin exposes
controller joint targets separately from measured joint positions; Fast-WAM
uses the targets from native ``joint_action.vector``.

The platform ``robot_spec.py`` connects the startup layers through callbacks.
For a WAM worker, the call chain is:

.. code-block:: text

   robot_spec._init_runtime()
     -> am_runtime.select_am(args, platform): resolve AMConfig and model options
     -> robots.runtime.try_spawn_server(spawn_fn)
          -> am_runtime.start_wam_service(config, output_dir)
               -> AMConfig.spawn_worker() -> ProcessDaemon.start()
               -> make_rpc_client()
               -> return daemon + RPC client
          -> register owned daemon
     -> robots.runtime.try_wait_server(post_fn)
          -> wait for readiness
          -> create platform WAM client and check control compatibility
          -> report ready to Dashboard

VLA launchers also use ``AMConfig.spawn_worker()``. Platforms retain their
transport and model command arguments, including LingBot's native WebSocket
connection and RoboCasa's session-enabled RPC. ``ProcessDaemon`` closes its
log on a failed spawn. The shared
``rpent/robots/runtime.py`` owns readiness, component status and group cleanup after
resource handoff. Borrowed endpoints return no owned daemon.

``am_runtime.add_am_args(parser, platform=...)`` registers supported backends
and common options. GPU selection and compatibility aliases are documented in
:doc:`../guides/cli`.

``AMConfig`` stores the resolved backend, platform, endpoint, checkpoint,
Python, working directory, GPU and additional worker arguments. Model defaults
are resolved without modifying the parsed namespace, so Dashboard reuse does
not mistake defaults for explicit options. WAM ``runtime_config.py`` modules
provide model-specific defaults and worker arguments; VLA platform launchers
retain their native command construction.

Add a VLA
---------

Because the model runs in its own process, adding a model-based
primitive requires a few additional components:

1. **Write ``vla_server.py``.** This process owns only the model weights
   and CUDA context. Use
   :class:`rpent.robots.components.am_facade_base.BaseVLAFacade` as the base
   class, implement ``predict``, and register any additional model RPCs by
   extending ``_register_rpc``:

   - The default transport is **HTTP** (JSON over ``POST /call``),
     which works well for flat ``image + state`` payloads such as the
     LIBERO / Pi0.5 pattern.
   - Switch to **socket RPC** (``--transport socket``) if your obs is
     a nested dict of numpy arrays with history stacks (avoids the
     JSON re-encode overhead).

   ``BaseVLAFacade`` registers ``vla.predict`` and serializes model calls.
   Passing ``model_meta=...`` to its constructor also registers the read-only
   ``vla.get_model_meta`` route; the model defines the metadata fields.
   Its inherited ``RpcFacade.serve`` handles transport binding, ``healthz``,
   ``shutdown``, parent-death detection, and resource cleanup.

2. **Write a model client.** Subclass
   :class:`rpent.robots.components.am_client_base.BaseVLAClient`, which
   provides the common ``vla.predict`` call, and add only the
   environment-specific input / output adaptation. See
   ``rpent.robots.components.pi05_vla_client.Pi05VLAClient`` for the LIBERO
   implementation.

3. **Add a method to the primitives.** In the current
   robot's primitives class, call the model client, pass
   the returned action chunk to the environment, and return a
   ``ToolResult``. The model client API is
   :meth:`rpent.robots.components.pi05_vla_client.Pi05VLAClient.predict`,
   which reads the instruction from ``env_obs["task_descriptions"]`` and
   returns a ``[chunk, action_dim]`` numpy action chunk (batch dim already
   stripped):

   .. code-block:: python

      @tool
      def mymodel_pick(self, target: str) -> ToolResult:
          """Pick the requested target using the model."""
          env_obs = self._env.get_obs()
          env_obs["task_descriptions"] = f"pick {target}"
          chunk = self._model.predict(env_obs)
          self._env.chunk_step(chunk)
          return ToolResult(data={"model": "mymodel", "target": target})

4. **Register the declared tool in the toolkit.** Follow the
   same pattern as for a scripted primitive.

5. **Wire the components together in ``robot_spec.py``.** The
   robot's ``get_toolkit`` builds the toolkit with
   ``runtime_kwargs``:

   .. code-block:: python

      def get_toolkit(*, runtime_kwargs, dashboard_events, config):
          from robots.myrobot.toolkit import MyRobotToolkit
          from rpent.memory import MemoryManager

          return MyRobotToolkit(
              runtime_kwargs=runtime_kwargs,
              dashboard_events=dashboard_events,
              memory=MemoryManager(config.prompt_vars["memory_dir"]),
          )

   The robot package's ``_init_runtime`` builds
   ``runtime_kwargs``, for example
   ``{"env": MyRobotEnvClient(...), "model": MyModelClient(...)}``.
   The toolkit constructor then forwards it to the primitives.

For existing-service deployment and endpoint examples, see
:doc:`../guides/advanced_deployment`. Stateful models also need the per-client
lifecycle hooks in :doc:`action_model_reference`.

Add a WAM
---------

Cosmos Policy and Cosmos3 support LIBERO and LIBERO-PRO; Fast-WAM supports LIBERO,
LIBERO-PRO and RoboTwin. Each model/platform pair requires a matching checkpoint.

``cosmos-policy`` uses NVIDIA's released ``Cosmos-Policy-LIBERO-Predict2-2B``
checkpoint and official LIBERO inference API. ``cosmos3`` connects to a
separately deployed SGLang ``/v1/actions/generations`` service using RLinf's
``Cosmos3SGLangAdapter`` and HTTP client. RLinf handles image composition,
request construction, action denormalization and rotation conversion; its
``prepare_actions_for_libero`` also supplies the simulator's gripper convention.
RPent reuses its existing LIBERO client and maps observations and predictions
at that boundary. These backends require different checkpoints.

1. Create a model package under ``rpent/robots/components/``. Its
   ``server.py`` subclasses ``BaseWAMFacade`` and implements
   ``predict_native``; provide a required ``(encode, decode)`` adapter pair.
2. Register each supported platform in the model's ``ADAPTERS`` mapping
   using ``WAMAdapterSpec`` from ``am_facade_base.py``. The model metadata factory declares checkpoint
   identity, camera/state requirements, native control and executable chunk size.
   Encode physical observations into model inputs; decode predictions into the
   declared platform action format.
3. Reuse a platform's ``wam_client.py`` when its observation and control
   contracts fit. ``BaseWAMClient`` fetches ``wam.get_model_meta`` once at
   initialization; the platform checks control compatibility before executing
   predictions. The client retains metadata in ``model_meta``.
4. Add model deployment options in ``runtime_config.py`` and register the
   backend in ``am_runtime.WAM_BACKENDS``; model-specific launch logic stays
   in the model package. Declare session usage in the
   model package, and implement ``reset_native`` if inference retains
   session history.
5. Wire the selected backend into the platform's runtime and tool execution.
   Reset model history at episode boundaries and close clients when finished.
   Every toolkit requires a ``MemoryManager``.

The WAM wire protocol, lifecycle, and platform checklist are in
:doc:`action_model_reference`. Its deployment section covers standalone workers
and per-run worker startup.

.. _wam-protocol:

Test
----

Extend the existing adapter, RPC and platform tests for each new model/platform
pair. Test locations, GPU prerequisites, commands and the distinction between
integration checks and task-success benchmarks are documented in
``tests/README.md``.

Troubleshooting and next steps
------------------------------

- **The worker starts but every prediction is rejected.** Check that the
  adapter's declared control mode and the platform's ``control.py`` describe
  the same action layout.
- **The environment executes the wrong number of steps.** The worker's chunk
  size and the platform's ``chunk_step`` length must match; do not trim inside
  the adapter unless the model contract says to.
- **Stateful predictions drift between episodes.** Reset model history at the
  episode boundary; see ``reset_native`` in :doc:`action_model_reference`.
- **The service works alone but not with RPent.** Compare the endpoint protocol
  (HTTP or socket) and the model metadata returned by ``wam.get_model_meta``.

Next: deploy an existing service in :doc:`../guides/advanced_deployment`, or
review the protocol and lifecycle in :doc:`action_model_reference`.
