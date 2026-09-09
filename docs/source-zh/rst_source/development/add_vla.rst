添加 VLA 后端
==============

在 RPent 中，*VLA 后端*（Vision-Language-Action 模型）把训练好的策略
（Pi0.5 / RLDX-1 / LingBot-VLA 等）包装成 RPC 服务，对上层 primitives 层
（``run_vla`` / ``pi0_pick`` / ``rldx_skill`` / ``lingbot_act``）暴露
统一的 ``predict`` 接口。本页讲如何基于统一基类
（:mod:`rpent.robots.components.vla_facade_base` /
:mod:`rpent.robots.components.vla_client_base`）添加新的 VLA 后端。

.. contents::
   :local:
   :depth: 2

重要规则
--------

**1. 模型在子类 ``__init__`` 中加载.**

加载策略是子类的事——加载方式、模型属性名都由子类决定. 子类在
``__init__`` 中自行加载模型, 之后 ``predict`` 直接读它. 不要在
``predict`` 里懒加载, 避免首次调用延迟和并发竞争.

**2. RPC 路由用注册字典.**

``_dispatch`` 用注册字典（``self._rpc``）替代 ``if method == "predict"``
链. 子类在 ``_register_rpc`` 中注册自己的方法, 所有 handler 必须接受
``session_id`` kwarg（VLA 不需要时忽略）. 子类重写 ``_register_rpc``
时应先调 ``super()._register_rpc()`` 再追加自己的 handler, 避免漏注册
基类已注册的 ``predict``.

**3. predict 的 obs / options / 返回值结构后端特有.**

不同模型的 obs 输入和 action 输出结构天然不同（取决于模型原生接口）.
基类只暴露抽象 ``predict``, 签名固定为
``predict(self, obs, options, *, session_id=None)``; obs 和返回值的
具体结构由后端决定, 调用方按后端特有结构处理.

**4. session 隔离: VLA 分为有 / 无 session 两类.**

VLA 后端根据策略状态是否按客户端隔离，分为两类:

- **无 session**: 后端不保存按客户端隔离的策略 memory, ``predict`` 忽略
  ``session_id``. 大多数 VLA 后端属于这类.
- **有 session**: 后端有按客户端隔离的策略状态（如 RLDX 的
  memory/RTC）, 需要 ``session_id`` 隔离不同客户端的策略状态,
  session 结束时还要清理该客户端的策略状态.

两类后端的 ``session_id`` 都由 RPC facade 从连接派生, 客户端**不**传——
facade 的 ``_dispatch`` 收到 RPC 调用时从连接派生 ``session_id``, 作为
kwarg 传给 ``predict`` handler. 有 session 的后端在 ``predict`` 里用
``session_id`` 隔离策略状态; 无 session 的后端忽略它.

完整的有 session 后端开发指南见下文
「带会话状态的 VLA 后端（按客户端隔离策略状态）」一节.

基类
----

统一基类已落地到 ``rpent/robots/components/`` 下两个文件:

- :mod:`rpent.robots.components.vla_facade_base` —
  :class:`~rpent.robots.components.vla_facade_base.BaseVLAFacade`（server 侧）
- :mod:`rpent.robots.components.vla_client_base` —
  :class:`~rpent.robots.components.vla_client_base.BaseVLAClient`（client 侧）

BaseVLAFacade（server 侧）
~~~~~~~~~~~~~~~~~~~~~~~~~~

继承 :class:`~rpent.utils.rpc.RpcFacade`, 提供框架层:

- ``__init__(*, enable_sessions=False, session_timeout_s=3600.0)``:
  初始化 ``self._rpc = {}`` 并调 ``_register_rpc()``; ``enable_sessions``
  / ``session_timeout_s`` 透传给 :class:`~rpent.utils.rpc.RpcFacade`,
  需要按客户端隔离会话状态的后端（如 robocasa）传
  ``enable_sessions=True``
- 抽象方法 ``predict(self, obs, options, *, session_id=None)`` —
  子类必须实现实际推理
- ``_register_rpc()``: 默认注册 ``vla.predict`` -> ``self.predict``,
  子类可重写追加（重写时先调 ``super()._register_rpc()``）
- ``_dispatch(self, method, args, kwargs, *, session_id=None)``:
  从 ``self._rpc`` 取 handler, 用 ``self._lock`` 串行化, 把
  ``session_id`` 作为 kwarg 传给所有 handler（readonly 方法也要
  接受该 kwarg, 不需要时忽略）
- 子类自行在 ``__init__`` 中加载模型
- 可选钩子 ``_on_session_drop(self, session_id)``: session 被
  ``session.close`` RPC 或空闲超时清理时触发, 有 session 的后端
  在这里清掉该客户端的策略状态（见下节）

BaseVLAClient（client 侧）
~~~~~~~~~~~~~~~~~~~~~~~~~

薄包装 :class:`~rpent.utils.rpc.RpcClient`:

- ``__init__(self, client)``: 接受一个 ``RpcClient`` 实例
- ``_TIMEOUT_S = {"default": 30.0, "predict": 120.0}`` —
  按方法分配超时, ``predict`` 默认 120s（VLA 推理较慢）
- ``predict(self, obs, options=None)``: 调
  ``self._client.call("vla.predict", args=(obs, options),
  timeout_s=self._TIMEOUT_S["predict"])``
- 客户端**不**传 ``session_id``（由 facade 注入）

接入步骤
--------

1. 继承 :class:`~rpent.robots.components.vla_facade_base.BaseVLAFacade`, 在
   ``__init__`` 中加载模型, 实现 ``predict``:

   .. code-block:: python

      from rpent.robots.components.vla_facade_base import BaseVLAFacade

      class MyVLAFacade(BaseVLAFacade):
          def __init__(self, *, model_path: str, device: str = "cuda"):
              super().__init__(device=device)
              self.policy = load_my_policy(model_path, device=device)

          def predict(self, obs, options, *, session_id=None):
              return self.policy.run(obs)

2. 注册额外 RPC 方法（可选）. 如果后端需要暴露 ``get_model_meta`` 等,
   在子类 ``_register_rpc`` 中追加:

   .. code-block:: python

      def _register_rpc(self):
          super()._register_rpc()
          self._rpc["vla.reset_session"] = self.reset_session
          self._rpc["vla.get_model_meta"] = self.get_model_meta

      def reset_session(self, *, session_id=None):
          ...

      def get_model_meta(self, *, session_id=None):
          return {"action_dim": ..., "horizon": ...}

   所有 handler 必须接受 ``session_id`` kwarg. 有 session 的后端如需
   ``reset_session`` 额外 RPC, 见下节.

3. 继承 :class:`~rpent.robots.components.vla_client_base.BaseVLAClient`（可选）.
   如果客户端需要额外方法（如 ``reset_session``）, 继承后追加:

   .. code-block:: python

      from rpent.robots.components.vla_client_base import BaseVLAClient

      class MyVLAClient(BaseVLAClient):
          def reset_session(self):
              return self._client.call(
                  "vla.reset_session",
                  timeout_s=self._TIMEOUT_S["default"],
              )

4. 启动 server. 在 ``main()`` 中构造 facade 并调 ``serve``:

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

   需要按客户端隔离会话状态时, 见下一节「带会话状态的 VLA 后端」的完整
   启动方式（构造 facade 传 ``enable_sessions=True`` 和
   ``session_timeout_s``, ``serve`` 传 ``session_sweep_s``）.

带会话状态的 VLA 后端（按客户端隔离策略状态）
------------------------------------------------

这类后端（如 RoboCasa 的 RLDX-1，策略带 memory/RTC）需要按客户端
隔离策略状态。完整接入分四块：

**A. 构造时启用 session 管理.**

.. code-block:: python

   class MyVLAFacade(BaseVLAFacade):
       def __init__(self, *, model_path: str, session_timeout_s=3600.0):
           super().__init__(
               enable_sessions=True,
               session_timeout_s=session_timeout_s,
           )
           self.policy = load_my_policy(model_path)

``enable_sessions=True`` 让基类的 ``_dispatch`` 走 session 分支:
每连接持有自己的 ``session_id``, 每次调用校验并刷新 ``last_active``.

**B. ``predict`` 用 server 注入的 session_id 隔离策略状态.**

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

必须**拒绝**调用方传入的 ``session_ids``（防止客户端伪造值串到
别的 session）, 再强制覆写为 ``[session_id]``. 这里的 ``session_id``
是 facade 注入的, 不要从 ``options`` 里读.

**C. ``reset_session`` 只重置策略状态, 不销毁 session.**

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

``reset_session`` 是 predict 的 session_ids 注入镜像, 同样用
``session_id`` 定位策略状态. 它和 ``_on_session_drop`` 的区别在于
session 本体保持存活, 后续调用继续用.

**D. ``_on_session_drop`` 在 session 结束时清理策略状态.**

.. code-block:: python

   def _on_session_drop(self, session_id):
       """Fire when the session is closed or idle-expired."""
       self.policy.reset({"session_ids": [session_id]})

这个钩子在两条路径触发: 客户端调用 ``session.close`` RPC（进程正常退出）
和 sweep 线程的空闲超时清理（进程崩溃、连接断开的兜底）. 用途是
释放该客户端的策略 memory/RTC, 避免状态残留.

**E. ``serve`` 传 ``session_sweep_s`` 定期清理过期 session.**

.. code-block:: python

   facade.serve(
       transport=args.transport,
       host=args.host,
       port=args.port,
       parent_watch=args.parent_watch,
       session_sweep_s=args.session_sweep_s,  # 必须 > 0
   )

``session_timeout_s`` 定义空闲超时, ``session_sweep_s`` 定义 sweep
线程的扫描周期; 空闲超过 ``session_timeout_s`` 的 session 被 drop,
触发 ``_on_session_drop``. ``session_sweep_s`` 必须为正数, 否则
:meth:`~rpent.utils.rpc.RpcFacade.serve` 抛 ``ValueError``.

关键约束
--------

- ``predict`` 签名固定: ``predict(self, obs, options, *, session_id=None)``,
  子类不能改签名
- ``session_id`` 由 facade 注入, ``predict`` 实现里不要从 ``options``
  读 ``session_ids``——如果需要 session 隔离, 直接用入参的
  ``session_id``
- 模型在子类 ``__init__`` 中加载, 不要在
  ``predict`` 里懒加载
- ``_register_rpc`` 重写时必须先调 ``super()._register_rpc()``, 再追加
  自己的 handler
- ``_dispatch`` 所有 handler 必须接受 ``session_id`` kwarg（不需要时
  忽略）
- 客户端 ``predict`` 不传 ``session_id``——由 facade 从连接派生后
  注入到 server 端 handler
- ``_TIMEOUT_S["predict"]`` 默认 120s, 如果模型推理更慢, 子类可重写
  ``_TIMEOUT_S`` 调大
- 有 session 的后端: 构造传 ``enable_sessions=True`` +
  ``session_timeout_s``, ``serve`` 必须传 ``session_sweep_s``（> 0）;
  ``predict`` / ``reset_session`` 强制覆写 ``session_ids`` 为
  ``[session_id]`` 并拒绝客户端传入; ``_on_session_drop`` 里清策略状态
- 无 session 的后端: ``predict`` 忽略 ``session_id``, 构造
  ``enable_sessions`` 保持默认 ``False``, ``serve`` 不传
  ``session_sweep_s``
