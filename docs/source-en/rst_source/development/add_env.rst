Add an Env Backend
==================

In RPent, an *env backend* wraps a robot simulator (gym / robosuite / an
external physics engine) as an RPC service that exposes a unified
``reset`` / ``step`` / ``chunk_step`` interface to the primitives layer.
This page explains how to add a new env backend on top of the shared base
classes (:mod:`rpent.robots.components.env_facade_base` /
:mod:`rpent.robots.components.env_client_base`).

.. contents::
   :local:
   :depth: 2

Key rules
---------

**1. Split responsibilities between client and server.**

The server wraps the env's low-level execution and returns results; the
core execution logic and state caching live on the client side. The server
must serialize non-read-only operations. ``last_obs`` and other cache
variables live **only on the client side**. The server is stateless (apart
from the env's own physical state) and re-reads the env on every request.
``BaseEnvFacade`` does **not** initialize ``self.last_obs``; the base
``chunk_step`` does **not** write those fields either (it raises
``NotImplementedError``, and subclass implementations should not write them
either).

Why:

- **Concurrent clients**: when several ``RpcClient`` connections attach to
  one server, each client keeps its own cache and they do not contaminate
  each other. A server-side cache would be overwritten across clients.
- **Server restart recovery**: after a crash and restart, a client can just
  ``reset`` to rebuild state. A server-side cache would be lost on restart
  while the client still holds a stale copy.
- **Clear ownership**: the server only "runs env actions and returns obs";
  the client decides "how to use and cache the obs".

If ``chunk_step`` embeds rendering, base the results on local variables
within that RPC call — do not write them to ``self``.

**2. Route RPCs through the registration dict.**

``RpcFacade._dispatch`` routes through the registration dict (``self._rpc``)
instead of dynamic ``getattr`` dispatch. Subclasses must **not** override
``_dispatch``; register methods in ``_register_rpc`` instead. When
overriding ``_register_rpc``, call ``super()._register_rpc()`` first and
then add your own handlers, so you do not drop the base routes.

**3. ``expected_meta`` handshake.**

The client constructor takes ``expected_meta`` (the caller's expectation of
the server config). ``BaseEnvClient.__init__`` immediately calls
``env.get_env_meta`` to fetch the server's actual config and asserts that it
equals ``expected_meta`` exactly; a mismatch fails the assert.

Why:

- **Fail fast**: config mismatches (e.g. ``camera_h`` / ``camera_w`` /
  ``action_dim``) surface at the handshake instead of crashing mid-rollout,
  avoiding wasted GPU time before a client / server version skew is found.
- **Clear ownership**: the server only reports its own config; the client
  decides whether that config matches the caller's expectation. Validation
  lives on the client and does not pollute the server.
- **Decoupling**: the server config is not hard-coded into the client base
  class — each caller passes its own ``expected_meta`` and may have
  different expectations.

**4. (Optional) EGL single-thread dispatch (GPU-rendering backends only).**

In multi-GPU / EGL environments the MuJoCo EGL context must stay on one
thread. If your backend renders with EGL, mix
:class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin` into your
facade class (**before** ``BaseEnvFacade``) and inherit the ``serve`` it
overrides — it runs the transport server on a daemon thread but executes
every dispatch serially on the thread that called ``serve`` (normally the
process main thread), keeping the EGL context on one thread (see robocasa's
``RoboCasaEnvFacade``). Backends that do not need EGL keep the plain
``serve`` inherited from ``BaseEnvFacade``.

Base classes
------------

The shared base classes live under ``rpent/robots/components/``:

- :mod:`rpent.robots.components.env_facade_base` —
  :class:`~rpent.robots.components.env_facade_base.BaseEnvFacade` (server side)
- :mod:`rpent.robots.components.env_client_base` —
  :class:`~rpent.robots.components.env_client_base.BaseEnvClient` (client side)

BaseEnvFacade (server side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subclasses :class:`~rpent.utils.rpc.RpcFacade` and provides the framework
layer:

- ``__init__()``: calls ``super().__init__()`` then ``_register_rpc()``.
  Env servers are not session-aware, so the constructor takes no arguments.
- Abstract methods ``get_env_meta`` / ``reset`` / ``step`` / ``chunk_step``
  / ``get_camera_meta`` / ``render_camera`` / ``get_task_language`` —
  subclasses must implement them
- ``_register_rpc()``: by default registers ``env.get_env_meta`` /
  ``env.reset`` / ``env.step`` / ``env.chunk_step`` /
  ``env.get_task_language`` / ``env.get_camera_meta`` /
  ``env.render_camera``, and adds ``env.get_env_meta`` /
  ``env.get_task_language`` / ``env.get_camera_meta`` /
  ``env.render_camera`` to ``_readonly_methods`` (safe to run concurrently
  with other reads). Subclasses may override to add routes (call
  ``super()._register_rpc()`` first)
- ``_dispatch`` (inherited from :class:`~rpent.utils.rpc.RpcFacade`, **do
  not override**): looks up the handler in ``self._rpc`` and serializes with
  ``self._dispatch_lock`` — methods in ``_readonly_methods`` run under the
  shared read lock, everything else under the exclusive write lock
- ``serve``: inherited from :class:`~rpent.utils.rpc.RpcFacade`, handling
  business calls concurrently. Subclasses that need EGL single-threading mix
  in :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin`
  (before ``BaseEnvFacade``); it overrides ``serve`` to run every dispatch
  on the main thread (see robocasa)
- ``close()``: the **process-cleanup hook** inherited from
  :class:`~rpent.utils.rpc.RpcFacade` (called when ``serve`` exits), **not**
  an RPC method. Subclasses may override it to release env resources.

BaseEnvClient (client side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A thin wrapper around :class:`~rpent.utils.rpc.RpcClient`:

- ``__init__(self, client, *, expected_meta: dict)``: takes an
  ``RpcClient``, calls ``env.get_env_meta`` and asserts the server meta
  equals ``expected_meta`` exactly, then calls ``reset()`` to initialize
  ``self.last_obs``
- ``_TIMEOUT_S = {"default": 30.0, "env.reset": 120.0, "env.step": 60.0,
  "env.chunk_step": 120.0, "env.render_camera": 120.0}`` — per-method
  timeouts
- ``last_obs``: a public attribute — the client-side cache. ``reset`` /
  ``step`` / ``chunk_step`` all update it, so callers can read
  ``client.last_obs`` without another RPC
- ``reset()`` / ``step(flat_action)`` / ``chunk_step(flat_actions, *,
  return_all_frames=False)`` — all update ``self.last_obs``
- ``get_camera_meta(camera_name, **kwargs)`` /
  ``render_camera(camera_name, **kwargs)`` / ``get_task_language()`` —
  thin wrappers over ``env.get_camera_meta`` / ``env.render_camera`` /
  ``env.get_task_language``

Integration steps
-----------------

1. Subclass :class:`~rpent.robots.components.env_facade_base.BaseEnvFacade`
   and implement the abstract methods ``get_env_meta`` / ``reset`` /
   ``step`` / ``chunk_step`` / ``get_camera_meta`` / ``render_camera`` /
   ``get_task_language``. The ``step`` / ``chunk_step`` arguments match your
   env's action space — how you derive the return values and what the tail
   of the returned tuple means is up to the subclass (different backends'
   ``env.step`` return different tuple lengths and done/term semantics).
   ``chunk_step``'s ``return_all_frames`` chooses whether the obs field is
   the final obs or a per-step list (``False`` saves GPU, ``True`` for
   recording):

   .. code-block:: python

      from rpent.robots.components.env_facade_base import BaseEnvFacade

      class MyEnvFacade(BaseEnvFacade):
          def __init__(self, env_cfg):
              super().__init__()
              self._env = build_my_env(env_cfg)

          def get_env_meta(self) -> dict:
              return {
                  "task_name": self._env.task_name,
                  "camera_h": 256,
                  "camera_w": 256,
                  "action_dim": self._env.action_dim,
              }

          def reset(self):
              return self._env.reset()

          def step(self, flat_action):
              # implement per your env's semantics
              ...

          def chunk_step(self, flat_actions, *, return_all_frames=False):
              # implement per your env's semantics; return_all_frames decides
              # whether the obs field is the final obs or a per-step list
              ...

          def get_camera_meta(self, camera_name, **kwargs):
              ...

          def render_camera(self, camera_name, **kwargs):
              ...

          def get_task_language(self):
              ...

   The ``chunk_step`` return value is a 5-positional tuple. The base
   convention is the gym-style ``(obs_or_list, reward, term, trunc, info)``
   (libero / robotwin use this shape); robocasa needs to report how many
   steps actually ran, so it returns ``(obs_or_list, reward, done, info,
   n_applied)``. Either way, callers unpack per their backend's convention —
   the base client only fixes ``result[0]`` as obs and ``result[1]`` as
   reward.

2. Register extra RPC methods (optional). If the backend exposes
   ``get_camera_transform`` / ``grasp_contact`` and friends, add them in the
   subclass ``_register_rpc``:

   .. code-block:: python

      def _register_rpc(self):
          super()._register_rpc()
          self._rpc["env.get_camera_transform"] = self.get_camera_transform
          self._rpc["env.grasp_contact"] = self.grasp_contact
          # only add to _readonly_methods when concurrency is truly safe
          self._readonly_methods.update(
              ["env.get_camera_transform", "env.grasp_contact"]
          )

      def get_camera_transform(self, camera_name, height=None, width=None):
          ...

      def grasp_contact(self):
          ...

3. EGL single-threading (GPU-rendering backends only). If you render with
   EGL, mix :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin`
   into your facade class (**before** ``BaseEnvFacade``) and inherit the
   ``serve`` it overrides — it runs the transport server on a daemon thread
   but executes every dispatch serially on the thread that called ``serve``,
   keeping the MuJoCo EGL context on one thread:

   .. code-block:: python

      from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin
      from rpent.robots.components.env_facade_base import BaseEnvFacade

      class MyEnvFacade(MainThreadServeMixin, BaseEnvFacade):
          ...

      facade.serve(transport="http", host=host, port=port)  # dispatch on the main thread

   The overridden ``serve`` keeps the same contract as
   :class:`~rpent.utils.rpc.RpcFacade`'s ``serve``: ``healthz`` /
   ``shutdown`` and parent-watch are still supported. Subclasses do **not**
   need to override ``serve`` to delegate — just inherit it (see
   ``RoboCasaEnvFacade`` in ``robots/robocasa/env_server.py``). Backends
   that do not need EGL single-threading keep the plain ``serve`` inherited
   from ``BaseEnvFacade``.

4. Subclass :class:`~rpent.robots.components.env_client_base.BaseEnvClient`
   (optional). If the client needs extra attributes or methods (e.g.
   ``eef_pos`` or a dedicated ``render_camera`` wrapper), add them after
   subclassing, reading ``self.last_obs`` directly to avoid extra RPCs:

   .. code-block:: python

      from rpent.robots.components.env_client_base import BaseEnvClient

      class MyEnvClient(BaseEnvClient):
          @property
          def eef_pos(self):
              return self.last_obs["robot0_eef_pos"]

          def custom_method(self, arg):
              return self._client.call(
                  "env.custom_method",
                  args=(arg,),
                  timeout_s=self._TIMEOUT_S["default"],
              )

5. Start the server. Build the facade in ``main()`` and call ``serve``:

   .. code-block:: python

      def main():
          parser = argparse.ArgumentParser()
          parser.add_argument("--transport", choices=["socket", "http"])
          parser.add_argument("--host", default="127.0.0.1")
          parser.add_argument("--port", type=int, required=True)
          parser.add_argument("--cuda-device", default="cuda")
          parser.add_argument("--parent-watch", action="store_true")
          args = parser.parse_args()

          facade = MyEnvFacade(env_cfg=...)
          facade.serve(
              transport=args.transport,
              host=args.host,
              port=args.port,
              parent_watch=args.parent_watch,
          )

Key constraints
---------------

- The server side does **not** cache ``last_obs`` or any obs cache — all
  caching lives on the client (``BaseEnvClient.last_obs``)
- When overriding ``_register_rpc``, call ``super()._register_rpc()`` first
  and then add your handlers; do **not** override ``_dispatch``
- The abstract method set is ``get_env_meta`` / ``reset`` / ``step`` /
  ``chunk_step`` / ``get_camera_meta`` / ``render_camera`` /
  ``get_task_language``; the base does **not** register ``env.close`` —
  ``close()`` is only the ``RpcFacade`` process-cleanup hook
- ``env.*`` handlers do **not** receive ``session_id`` (env servers are not
  session-aware; ``RpcFacade._dispatch_nosession`` passes only
  ``*args / **kwargs``)
- Backends that need EGL single-threading mix in ``MainThreadServeMixin``
  (before ``BaseEnvFacade``) and inherit its ``serve``; those that do not
  use the base ``serve``
- The ``expected_meta`` handshake is the client's job:
  ``BaseEnvClient.__init__`` immediately calls ``env.get_env_meta`` and
  asserts it equals ``expected_meta`` exactly, failing the assert on a
  mismatch
- ``last_obs`` is the client-side cache; ``reset`` / ``step`` /
  ``chunk_step`` all update it, and reading ``client.last_obs`` triggers no
  extra RPC
- If a subclass needs extra ``env.*`` RPCs, register them in
  ``_register_rpc`` — do not promote them to the base class
