Add a VLA Backend
=================

In RPent, a *VLA backend* (Vision-Language-Action model) wraps a trained
policy (Pi0.5 / RLDX-1 / LingBot-VLA and so on) as an RPC service that
exposes a unified ``predict`` interface to the primitives layer
(``run_vla`` / ``pi0_pick`` / ``rldx_skill`` / ``lingbot_act``). This page
explains how to add a new VLA backend on top of the shared base classes
(:mod:`rpent.robots.components.vla_facade_base` /
:mod:`rpent.robots.components.vla_client_base`).

.. contents::
   :local:
   :depth: 2

Key rules
---------

**1. Load the model in the subclass ``__init__``.**

Loading is the subclass's business — the loading method and model attribute
names are up to the subclass. The subclass loads the model in ``__init__``
and ``predict`` reads it directly afterward. Do not lazy-load inside
``predict``; it adds first-call latency and a concurrency race.

**2. Route RPCs through the registration dict.**

``_dispatch`` routes through the registration dict (``self._rpc``) instead
of an ``if method == "predict"`` chain. Subclasses register their methods in
``_register_rpc``. Session-enabled backends must accept a ``session_id``
kwarg in every handler (injected by the facade; ignore it when the VLA does
not need it); sessionless backends must **not** accept that kwarg. When
overriding ``_register_rpc``, call ``super()._register_rpc()`` first and
then add your own handlers, so you do not drop the base ``predict`` route.

**3. The obs / options / return structures of ``predict`` are
backend-specific.**

Different models have inherently different obs inputs and action outputs
(depending on the model's native interface). The base class only exposes the
abstract ``predict``, with the convention
``predict(self, obs, options, *, session_id=None)``; the concrete structures
of obs and the return value are backend-defined, and callers handle the
backend-specific structure.

**4. Session isolation: VLAs fall into two families.**

A VLA backend falls into one of two families depending on whether its policy
state is isolated per client:

- **Sessionless**: the backend keeps no per-client policy memory;
  ``predict`` ignores ``session_id``. Most VLA backends are sessionless.
- **Sessionful**: the backend has per-client policy state (e.g. RLDX's
  memory/RTC); ``session_id`` isolates different clients' policy state, and
  that client's state must be cleaned up when the session ends.

For both families, ``session_id`` is derived from the connection by the RPC
facade — the client does **not** pass it: the facade's ``_dispatch`` derives
``session_id`` from the connection on each RPC call and passes it as a kwarg
to the ``predict`` handler. Sessionful backends use ``session_id`` inside
``predict`` to isolate policy state; sessionless backends ignore it.

The full sessionful-backend guide is in the "Session-aware VLA backends
(per-client policy state)" section below.

Base classes
------------

The shared base classes live under ``rpent/robots/components/``:

- :mod:`rpent.robots.components.vla_facade_base` —
  :class:`~rpent.robots.components.vla_facade_base.BaseVLAFacade` (server side)
- :mod:`rpent.robots.components.vla_client_base` —
  :class:`~rpent.robots.components.vla_client_base.BaseVLAClient` (client side)

BaseVLAFacade (server side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subclasses :class:`~rpent.utils.rpc.RpcFacade` and provides the framework
layer:

- ``__init__(*, enable_sessions=False, session_timeout_s=3600.0)``:
  initializes ``self._rpc = {}`` and calls ``_register_rpc()``;
  ``enable_sessions`` / ``session_timeout_s`` are forwarded to
  :class:`~rpent.utils.rpc.RpcFacade`. Backends that isolate per-client
  session state (e.g. robocasa) pass ``enable_sessions=True``
- Abstract method ``predict(self, obs, options, *, session_id=None)`` —
  subclasses must implement the actual inference
- ``_register_rpc()``: by default registers ``vla.predict`` -> ``self.predict``;
  subclasses may override to add routes (call ``super()._register_rpc()``
  first)
- ``_dispatch`` (inherited from :class:`~rpent.utils.rpc.RpcFacade`, **do
  not override**): looks up the handler in ``self._rpc`` and serializes with
  ``self._dispatch_lock`` (methods in ``_readonly_methods`` run under the
  shared read lock, everything else under the exclusive write lock); when
  sessions are enabled it injects the caller's ``session_id`` as a kwarg
  into every handler
- The subclass loads the model itself in ``__init__``
- Optional hook ``_on_session_drop(self, session_id)``: fired when a session
  is cleaned up by the ``session.close`` RPC or idle timeout; sessionful
  backends clear that client's policy state here (see the next section)

BaseVLAClient (client side)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A thin wrapper around :class:`~rpent.utils.rpc.RpcClient`:

- ``__init__(self, client)``: takes an ``RpcClient`` instance
- ``_TIMEOUT_S = {"default": 30.0, "predict": 120.0}`` — per-method
  timeouts; ``predict`` defaults to 120 s (VLA inference is slow)
- ``predict(self, obs, options=None)``: calls
  ``self._client.call("vla.predict", args=(obs, options),
  timeout_s=self._TIMEOUT_S["predict"])``
- The client does **not** pass ``session_id`` (the facade injects it)

Integration steps
-----------------

1. Subclass :class:`~rpent.robots.components.vla_facade_base.BaseVLAFacade`,
   load the model in ``__init__``, and implement ``predict``:

   .. code-block:: python

      from rpent.robots.components.vla_facade_base import BaseVLAFacade

      class MyVLAFacade(BaseVLAFacade):
          def __init__(self, *, model_path: str, device: str = "cuda"):
              super().__init__()  # sessionless: enable_sessions defaults False
              self.policy = load_my_policy(model_path, device=device)

          def predict(self, obs, options, *, session_id=None):
              return self.policy.run(obs)

2. Register extra RPC methods (optional). If the backend exposes e.g.
   ``get_model_meta``, add it in the subclass ``_register_rpc``:

   .. code-block:: python

      def _register_rpc(self):
          super()._register_rpc()
          self._rpc["vla.reset_session"] = self.reset_session
          self._rpc["vla.get_model_meta"] = self.get_model_meta

      def reset_session(self, *, session_id=None):
          ...

      def get_model_meta(self, *, session_id=None):
          return {"action_dim": ..., "horizon": ...}

   Session-enabled backends must accept a ``session_id`` kwarg in every
   handler (sessionless backends do not). For the extra ``reset_session``
   RPC used by sessionful backends, see the next section.

3. Subclass :class:`~rpent.robots.components.vla_client_base.BaseVLAClient`
   (optional). If the client needs extra methods (e.g. ``reset_session``),
   subclass it and add them:

   .. code-block:: python

      from rpent.robots.components.vla_client_base import BaseVLAClient

      class MyVLAClient(BaseVLAClient):
          def reset_session(self):
              return self._client.call(
                  "vla.reset_session",
                  timeout_s=self._TIMEOUT_S["default"],
              )

4. Start the server. Build the facade in ``main()`` and call ``serve``:

   .. code-block:: python

      def main():
          parser = argparse.ArgumentParser()
          parser.add_argument("--transport", choices=["socket", "http"])
          parser.add_argument("--host", default="127.0.0.1")
          parser.add_argument("--port", type=int, required=True)
          parser.add_argument("--cuda-device", default="cuda")
          parser.add_argument("--model-path", required=True)
          parser.add_argument("--parent-watch", action="store_true")
          args = parser.parse_args()

          facade = MyVLAFacade(
              model_path=args.model_path, device=args.cuda_device
          )
          facade.serve(
              transport=args.transport,
              host=args.host,
              port=args.port,
              parent_watch=args.parent_watch,
          )

   When you need per-client session isolation, follow the full startup
   pattern in the next section (construct the facade with
   ``enable_sessions=True`` and ``session_timeout_s``; pass
   ``session_sweep_s`` to ``serve``).

Session-aware VLA backends (per-client policy state)
----------------------------------------------------

These backends (e.g. RoboCasa's RLDX-1, whose policy carries memory/RTC)
need per-client policy-state isolation. Full integration has five parts:

**A. Enable session management at construction.**

.. code-block:: python

   class MyVLAFacade(BaseVLAFacade):
       def __init__(self, *, model_path: str, session_timeout_s=3600.0):
           super().__init__(
               enable_sessions=True,
               session_timeout_s=session_timeout_s,
           )
           self.policy = load_my_policy(model_path)

``enable_sessions=True`` makes the base ``_dispatch`` take the session
branch: each connection holds its own ``session_id``, and every call
validates and refreshes ``last_active``.

**B. ``predict`` uses the server-injected session_id to isolate policy
state.**

.. code-block:: python

   def predict(self, obs, options, *, session_id=None):
       options = dict(options or {})
       if "session_ids" in options:
           raise ValueError(
               "predict options must not contain 'session_ids'; the "
               "server injects the caller's private session id"
           )
       options["session_ids"] = [session_id]
       actions, info = self.policy.get_action(obs, options=options)
       return actions

You must **reject** a caller-supplied ``session_ids`` (so a client cannot
forge a value and leak into another session), then overwrite it with
``[session_id]``. This ``session_id`` is injected by the facade — do not read
it from ``options``.

**C. ``reset_session`` resets only policy state, it does not destroy the
session.**

.. code-block:: python

   def reset_session(self, *, session_id=None):
       """Reset RLDX internal state (memory/RTC) for this session.

       Does NOT destroy the session — only resets the policy state.
       """
       self.policy.reset({"session_ids": [session_id]})
       return {"ok": True}

   def _register_rpc(self):
       super()._register_rpc()
       self._rpc["vla.reset_session"] = self.reset_session

``reset_session`` mirrors the ``session_ids`` injection in ``predict`` and
also locates policy state via ``session_id``. It differs from
``_on_session_drop`` in that the session itself stays alive and subsequent
calls keep using it.

**D. ``_on_session_drop`` cleans up policy state when a session ends.**

.. code-block:: python

   def _on_session_drop(self, session_id):
       """Fire when the session is closed or idle-expired."""
       self.policy.reset({"session_ids": [session_id]})

This hook fires on two paths: the client's ``session.close`` RPC (clean
process exit) and the sweep thread's idle-timeout cleanup (the fallback for
a crashed process / dropped connection). Its purpose is to release that
client's policy memory/RTC so no state is left behind.

**E. Pass ``session_sweep_s`` to ``serve`` to periodically reclaim expired
sessions.**

.. code-block:: python

   facade.serve(
       transport=args.transport,
       host=args.host,
       port=args.port,
       parent_watch=args.parent_watch,
       session_sweep_s=args.session_sweep_s,  # must be > 0
   )

``session_timeout_s`` defines the idle timeout and ``session_sweep_s`` the
sweep thread's scan interval; sessions idle for longer than
``session_timeout_s`` are dropped, firing ``_on_session_drop``.
``session_sweep_s`` must be positive, otherwise
:meth:`~rpent.utils.rpc.RpcFacade.serve` raises ``ValueError``.

Key constraints
---------------

- The ``predict`` signature convention is
  ``predict(self, obs, options, *, session_id=None)``; subclasses must not
  change it
- ``session_id`` is injected by the facade; do not read ``session_ids`` from
  ``options`` inside ``predict`` — if you need session isolation, use the
  incoming ``session_id`` directly
- Load the model in the subclass ``__init__``; do not lazy-load it inside
  ``predict``
- When overriding ``_register_rpc``, call ``super()._register_rpc()`` first
  and then add your own handlers
- Session-enabled backends: every handler must accept a ``session_id`` kwarg
  (injected by the facade; ignore it when unused). Sessionless backends:
  handlers must **not** accept that kwarg
- The client's ``predict`` does not pass ``session_id`` — the facade derives
  it from the connection and injects it into the server-side handler
- ``_TIMEOUT_S["predict"]`` defaults to 120 s; if your model is slower,
  override ``_TIMEOUT_S`` in the subclass
- Sessionful backends: construct with ``enable_sessions=True`` +
  ``session_timeout_s``; ``serve`` must pass ``session_sweep_s`` (> 0);
  ``predict`` / ``reset_session`` overwrite ``session_ids`` with
  ``[session_id]`` and reject client-supplied values; clear policy state in
  ``_on_session_drop``
- Sessionless backends: ``predict`` ignores ``session_id``; keep the default
  ``enable_sessions=False`` and do not pass ``session_sweep_s`` to ``serve``
