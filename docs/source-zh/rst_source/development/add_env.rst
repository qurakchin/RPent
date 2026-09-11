添加 env 后端
==============

在 RPent 中，*env 后端* 把机器人模拟器（gym / robosuite / 外部物理引擎）
包装成 RPC 服务，对上层 primitives 层暴露统一的 ``reset`` / ``step`` /
``chunk_step`` 接口。本页讲如何基于统一基类
（:mod:`rpent.robots.components.env_facade_base` /
:mod:`rpent.robots.components.env_client_base`）添加新的 env 后端。

.. contents::
   :local:
   :depth: 2

重要规则
--------

**1. client / server 侧分工.**

server 侧负责包装 env 的底层执行并返回, 核心执行逻辑和状态存储由 client 侧负责.
server 侧需要保证, 非 readonly 的操作必须串行执行。
``last_obs`` 等缓存变量 **只存在于 client 侧**。
server 是无状态的（除 env 本身的物理状态外），每次请求都重新读 env。
``BaseEnvFacade`` **不初始化** ``self.last_obs``；``chunk_step`` 的默认实现也
**不写这些字段（基类直接抛 ``NotImplementedError``, 子类实现时同样不应写）**。

原因:

- **多 client 并发**: 多个 ``RpcClient`` 连到同一 server 时, 每个 client
  维护自己的缓存, 互不污染. server 缓存会被并发 client 互相覆盖.
- **server 重启恢复**: server 崩溃重启后, client 重新 ``reset`` 即可重建
  状态. server 缓存则会在重启后失效, 但 client 不知情, 继续用旧缓存.
- **职责清晰**: server 只负责"执行 env 动作并返回 obs", client 负责
  "决定如何使用 obs 并缓存".

如果 ``chunk_step`` 内嵌渲染, 渲染结果应基于本次 RPC 调用内的临时
局部变量, 不要写 ``self``.

**2. RPC 路由用注册字典.**

``RpcFacade._dispatch`` 用注册字典（``self._rpc``）路由, 不再用
``getattr`` 动态分发。子类 **不要覆写** ``_dispatch``, 而应在
``_register_rpc`` 中注册自己的方法。子类重写 ``_register_rpc`` 时应先调
``super()._register_rpc()`` 再追加自己的 handler, 避免漏注册基类已注册的
方法。

**3. expected_meta 握手校验.**

client 构造时传入 ``expected_meta`` （调用方对 server 配置的预期）,
``BaseEnvClient.__init__`` 启动后立即调 ``env.get_env_meta`` 拿 server 实际
配置, 断言与 ``expected_meta`` 完全相等, 不匹配直接 assert。

原因:

- **fail-fast**: 配置不匹配（如 ``camera_h`` / ``camera_w`` /
  ``action_dim`` 对不上）在握手阶段就暴露, 而不是跑到 mid-rollout
  才崩, 避免浪费 GPU 算力后才发现 client / server 版本错位.
- **职责清晰**: server 只如实报告自己的配置, client 负责判断配置
  是否符合上层调用方预期. 校验在 client 侧, 不污染 server.
- **解耦**: server 配置不上提到 client 基类硬编码——调用方按自己
  需求传 ``expected_meta``, 不同调用方可以有不同预期.

**4. (可选) EGL 单线程派发（仅 GPU 渲染后端）.**

多 GPU/EGL 环境下, MuJoCo EGL context 必须留在同一线程. 如果你的
后端用 EGL 渲染, 把 :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin`
混入你的 facade 类（**先于** ``BaseEnvFacade``）, 直接继承它覆盖的
``serve``——它在守护线程跑 transport server, 但在调用 ``serve`` 的线程
（通常是主线程）串行执行每个 dispatch, 保证 EGL context 线程亲和（见
robocasa ``RoboCasaEnvFacade`` 的实现）. 不需要 EGL 的后端直接继承
``BaseEnvFacade`` 用默认 ``serve``.

基类
----

统一基类已落地到 ``rpent/robots/components/`` 下两个文件:

- :mod:`rpent.robots.components.env_facade_base` —
  :class:`~rpent.robots.components.env_facade_base.BaseEnvFacade` （server 侧）
- :mod:`rpent.robots.components.env_client_base` —
  :class:`~rpent.robots.components.env_client_base.BaseEnvClient` （client 侧）

BaseEnvFacade（server 侧）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

继承 :class:`~rpent.utils.rpc.RpcFacade`, 提供框架层:

- ``__init__()``: 调 ``super().__init__()`` 后调 ``_register_rpc()``。
  env server 不启用 session, 因此构造不接受参数。
- 抽象方法 ``get_env_meta`` / ``reset`` / ``step`` / ``chunk_step`` /
  ``get_camera_meta`` / ``render_camera`` / ``get_task_language`` — 子类
  必须实现
- ``_register_rpc()``: 默认注册 ``env.get_env_meta`` / ``env.reset`` /
  ``env.step`` / ``env.chunk_step`` / ``env.get_task_language`` /
  ``env.get_camera_meta`` / ``env.render_camera``, 并把
  ``env.get_env_meta`` / ``env.get_task_language`` /
  ``env.get_camera_meta`` / ``env.render_camera`` 加入
  ``_readonly_methods`` （可与其它读操作并发）。子类可重写追加（重写时先调
  ``super()._register_rpc()``）
- ``_dispatch`` （继承自 :class:`~rpent.utils.rpc.RpcFacade`, **不要覆写**）:
  从 ``self._rpc`` 取 handler, 用 ``self._dispatch_lock`` 串行化——
  ``_readonly_methods`` 里的方法走共享读锁, 其余走独占写锁
- ``serve``: 默认继承自 :class:`~rpent.utils.rpc.RpcFacade`, 业务调用并发
  处理. 需要 EGL 单线程的子类混入
  :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin`
  （先于 ``BaseEnvFacade``）, 它覆盖 ``serve`` 让每个 dispatch 在主线程
  串行执行（见 robocasa）
- ``close()``: 继承自 :class:`~rpent.utils.rpc.RpcFacade` 的 **进程清理钩子**
  （``serve`` 退出时调用）, **不是** RPC 方法。子类可重写以释放 env 资源。

BaseEnvClient（client 侧）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

薄包装 :class:`~rpent.utils.rpc.RpcClient`:

- ``__init__(self, client, *, expected_meta: dict)``: 接受一个
  ``RpcClient`` 实例, 调 ``env.get_env_meta`` 断言 server 返回的 meta 与
  ``expected_meta`` 完全相等, 然后调 ``reset()`` 初始化 ``self.last_obs``
- ``_TIMEOUT_S = {"default": 30.0, "env.reset": 120.0, "env.step": 60.0,
  "env.chunk_step": 120.0, "env.render_camera": 120.0}`` — 按方法分配超时
- ``last_obs``: 公开属性, client 侧缓存. ``reset`` / ``step`` /
  ``chunk_step`` 都会更新它, 调用方可直接访问 ``client.last_obs``
  避免额外 RPC
- ``reset()`` / ``step(flat_action)`` / ``chunk_step(flat_actions, *,
  return_all_frames=False)`` — 都更新 ``self.last_obs``
- ``get_camera_meta(camera_name, **kwargs)`` /
  ``render_camera(camera_name, **kwargs)`` / ``get_task_language()`` —
  ``env.get_camera_meta`` / ``env.render_camera`` /
  ``env.get_task_language`` 的薄包装

接入步骤
--------

1. 继承 :class:`~rpent.robots.components.env_facade_base.BaseEnvFacade`,
   实现抽象方法 ``get_env_meta`` / ``reset`` / ``step`` / ``chunk_step`` /
   ``get_camera_meta`` / ``render_camera`` / ``get_task_language``.
   ``step`` / ``chunk_step`` 的入参与你的 env 的 action 空间一致——
   具体怎么从你的 env 拿到返回值、返回元组的尾部语义由子类决定
   （不同后端的 env.step 返回元组长度、done/term 语义都不同）.
   ``chunk_step`` 的 ``return_all_frames`` 控制 obs 字段是最终 obs 还是
   每步 obs 列表（``False`` 省 GPU, ``True`` 用于录像）:

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
              # 子类按 env 语义实现
              ...

          def chunk_step(self, flat_actions, *, return_all_frames=False):
              # 子类按 env 语义实现；return_all_frames 决定 obs 字段是
              # 最终 obs 还是每步 obs 列表
              ...

          def get_camera_meta(self, camera_name, **kwargs):
              ...

          def render_camera(self, camera_name, **kwargs):
              ...

          def get_task_language(self):
              ...

   ``chunk_step`` 的返回值约定为 5 位置元组。基类沿用的是 gym 风格
   ``(obs_or_list, reward, term, trunc, info)`` （libero / robotwin 即此
   形状）；robocasa 因需要回报实际执行的步数, 返回
   ``(obs_or_list, reward, done, info, n_applied)``。无论哪种, 调用方按
   后端约定解包——基类 client 只固化 ``result[0]`` 是 obs、``result[1]``
   是 reward。

2. 注册额外 RPC 方法（可选）. 如果后端需要暴露 ``get_camera_transform`` /
   ``grasp_contact`` 等, 在子类 ``_register_rpc`` 中追加:

   .. code-block:: python

      def _register_rpc(self):
          super()._register_rpc()
          self._rpc["env.get_camera_transform"] = self.get_camera_transform
          self._rpc["env.grasp_contact"] = self.grasp_contact
          # 确认可安全并发读时, 才加入 _readonly_methods
          self._readonly_methods.update(
              ["env.get_camera_transform", "env.grasp_contact"]
          )

      def get_camera_transform(self, camera_name, height=None, width=None):
          ...

      def grasp_contact(self):
          ...

3. EGL 单线程（仅 GPU 渲染后端）. 如果用 EGL 渲染, 把
   :class:`~rpent.utils.rpc.main_thread_serve.MainThreadServeMixin` 混入
   你的 facade 类（**先于** ``BaseEnvFacade``）, 直接继承它覆盖的
   ``serve``——它在守护线程跑 transport server, 但在调用 ``serve`` 的线程
   串行执行每个 dispatch, 保证 MuJoCo EGL context 留在同一线程:

   .. code-block:: python

      from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin
      from rpent.robots.components.env_facade_base import BaseEnvFacade

      class MyEnvFacade(MainThreadServeMixin, BaseEnvFacade):
          ...

      facade.serve(transport="http", host=host, port=port)  # dispatch 在主线程串行

   mixin 覆盖的 ``serve`` 与 :class:`~rpent.utils.rpc.RpcFacade` 的
   ``serve`` 契约一致: 同样支持 ``healthz`` / ``shutdown`` 和 parent-watch。
   子类 **不需要重写** ``serve`` 来委托, 直接继承即可（参考
   ``robots/robocasa/env_server.py`` 的 ``RoboCasaEnvFacade``）。不需要
   EGL 单线程的后端直接继承 ``BaseEnvFacade`` 用默认 ``serve``。

4. 继承 :class:`~rpent.robots.components.env_client_base.BaseEnvClient`
   （可选）. 如果客户端需要额外属性或方法（如 ``eef_pos`` /
   ``render_camera`` 的专用封装）, 继承后追加, 直接读 ``self.last_obs``
   避免额外 RPC:

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

5. 启动 server. 在 ``main()`` 中构造 facade 并调 ``serve``:

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

关键约束
--------

- server 侧 **不缓存** ``last_obs`` 等 obs 缓存——所有缓存只在 client 侧
  （``BaseEnvClient.last_obs``）
- ``_register_rpc`` 重写时必须先调 ``super()._register_rpc()``, 再追加
  自己的 handler; **不要覆写** ``_dispatch``
- 抽象方法集合为 ``get_env_meta`` / ``reset`` / ``step`` / ``chunk_step`` /
  ``get_camera_meta`` / ``render_camera`` / ``get_task_language``; 基类 **不注册**
  ``env.close``——``close()`` 只是 ``RpcFacade`` 的进程清理钩子
- ``env.*`` handler **不接收** ``session_id`` （env server 不启用 session,
  ``RpcFacade._dispatch_nosession`` 只透传 ``*args / **kwargs``）
- 需要 EGL 单线程的后端混入 ``MainThreadServeMixin`` （先于
  ``BaseEnvFacade``）并直接继承其 ``serve``; 不需要的用基类默认 ``serve``
- ``expected_meta`` 握手是 client 侧职责: ``BaseEnvClient.__init__`` 启动后
  立即调 ``env.get_env_meta`` 断言与 ``expected_meta`` 完全相等, 不匹配直接
  assert
- ``last_obs`` 是 client 侧缓存, ``reset`` / ``step`` / ``chunk_step``
  都会更新它; 调用方读 ``client.last_obs`` 不触发额外 RPC
- 子类需要额外的 ``env.*`` RPC, 在 ``_register_rpc`` 中注册, 不上提到基类
