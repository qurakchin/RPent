核心接口
========

给新机器人或新 primitive 接入 RPent 时，需要对接的接口如下。具体操作见
:doc:`add_robot`、:doc:`add_primitive`；仓库分层见 :doc:`architecture`。

机器人入口
----------

把包放到 ``robots/<robot>/`` 后，包的 ``__init__.py`` 会重导出
``robot_spec.py`` 中实现的两个函数，供 ``main.py`` 调用：

.. code-block:: python

   def get_robot_spec() -> RobotSpec: ...
   def get_toolkit(
       *,
       primitives_kwargs,
       dashboard_events: DashboardEventSink,
       config: RunConfig,
   ): ...

``get_robot_spec`` 返回 ``RobotSpec``，其中你需要提供：

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - 字段或钩子
     - 你要做什么
   * - ``name``
     - 机器人名，对应 ``--robot``。
   * - ``prompts``
     - ``PromptBundle``：``system`` 与 ``user`` 两套 prompt 工厂（见
       ``robots/<robot>/prompt_bundle.py``）。
   * - ``dashboard``
     - 可选的 Dashboard 描述。设为 ``None`` 时，该机器人不支持 Dashboard 控制；
       否则由该 spec 定义任务命令与字段、runtime components 和 frame channels。
   * - ``add_cli_args``
     - 注册本机器人的 CLI 参数（如 ``--suite``、``--env-endpoint``）。
   * - ``parse_config``
     - 校验参数并返回 ``RunConfig``；``recipe_tag``、``output_dir``、``prompt_vars``
       三项需由你正确填写（供 prompt 模板插值）。
   * - ``init_runtime``
     - 启动或连接全部 runtime components，或只处理指定名称的子集，并构造对应的
       ``primitives_kwargs``。普通 CLI 传 ``None``；Dashboard 从 spec 得到显式声明
       的 shared 和 unique 子集后分别传入。``DashboardEventSink`` 用于上报运行时状态。

``get_toolkit`` 一般只需把 ``primitives_kwargs`` 传给机器人子类；
``dashboard_events`` 和 ``config`` 由当前 runner 传入。它需要构造一个
:class:`~rpent.memory.MemoryManager` （root 取自
``config.prompt_vars["memory_dir"]``，未设置时回退到
``get_memory_dir(robot_name)``）并传给 toolkit。Memory 访问权限在
``MemoryManager`` 上配置。如果某个机器人还需要额外参数，可以继续声明
keyword-only 参数；例如 LIBERO 还使用 ``mode``、``attempts_per_session`` 和
``state_output_dir``。

参考实现：``robots/libero/robot_spec.py``。

Planner
-------

多数用户用内置 ``api``、``claude_code``、``codex``，见
:doc:`../usage/configure_planner`。自定义 planner 才需实现
``rpent.planner.base.Planner``：

.. code-block:: python

   def solve(
       self,
       *,
       system_prompt: str,
       user_message: str,
       toolkit: Toolkit,
       max_turns: int,
       input_queue=None,
       dashboard_interaction=None,
   ) -> PlannerResult: ...

约定：用 ``toolkit.get_tools_spec()`` 把工具交给模型；每次调用 ``toolkit.execute_tool(name, input_dict)``；
把结果喂回模型；在 ``finish`` 工具或轮次用尽时返回 ``PlannerResult``。

工具集
------

在 ``robots/<robot>/toolkit.py`` 里继承 ``Toolkit``，用 ``add_tool`` 注册机器人工具：

.. code-block:: python

   def add_tool(self, name: str, spec: dict, handler) -> None: ...

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - 参数
     - 含义
   * - ``name``
     - LLM 看到的工具名。
   * - ``spec``
     - 工具说明与参数 schema（``name``、``description``、``input_schema``）。
   * - ``handler``
     - 执行逻辑，须返回 ``dict``。任务结束时在该 ``dict`` 里设 ``_finish``；
       需要回传相机图时可设 ``_image_bytes`` 等字段。

基类已注册公共文件工具；子类 ``super().__init__()`` 后追加本机器人工具即可。逐步状态与
``view_env_state`` 见 :doc:`add_primitive`。

进程间通信
----------

接已有server或写 ``env_server`` / ``vla_server`` 时关注下面两点。

客户端端点（在 ``add_cli_args`` 中暴露，并在适用的普通 CLI 或 Dashboard
runtime 钩子中解析）：

.. code-block:: text

   [protocol://]host:port    # 未写协议时默认为 http

常见：``--env-endpoint``、``--vla-endpoint``。``http`` 为默认，走 ``POST /call``
传 JSON，其中 NumPy 数组编码为 ``{"__ndarray__": <base64>, "dtype": ..., "shape": ...}``；
观测数据很大、或是多帧堆叠的嵌套 NumPy 字典时可改 ``socket``，用带长度前缀的
pickle 数据帧传输，省掉反复的 JSON 编解码。pickle 不适合不可信输入，socket 只应连接可信端点。

服务端：env 后端继承
:class:`rpent.robots.components.env_facade_base.BaseEnvFacade`，VLA 后端继承
:class:`rpent.robots.components.vla_facade_base.BaseVLAFacade` （两者都继承
``rpent.utils.rpc.RpcFacade``）。业务方法在 ``_register_rpc`` 中注册（基类已注册
``env.reset`` / ``env.step`` / ``env.chunk_step``、``vla.predict`` 等公共路由），
**不要覆写** ``_dispatch``。env 的 handler 不接收 ``session_id``；需要按 client
隔离状态的 VLA 后端（如带 memory buffer 的）在 ``__init__`` 传
``enable_sessions=True``、``serve`` 传正数 ``session_sweep_s``，并重写
``_on_session_drop``——facade 会把 caller 的 ``session_id`` 注入所有 handler。
``healthz`` / ``shutdown`` 不必在子类里写 —— base
会处理；启用 session 时 ``session.register`` / ``session.close`` 也由 base
处理。

细节见 :doc:`add_robot` 中的 env_server 与 vla_server 章节。
