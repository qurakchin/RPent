添加机器人或仿真环境
==============================

本指南介绍如何将新的真机或仿真环境接入 RPent，让语言模型通过工具调用完成任务。完整的参考实现见 ``robots/libero/``。

.. page-head::
   :for: 要新增真机或仿真平台接入的开发者
   :outcome: 注册 ``RobotSpec``、实现环境 RPC 两端、提示词和工具集，并补充测试
   :read-when: 新增机器人包，或适配 RLinf 环境时
   :skip-when: 只使用已支持的平台；看该平台页面即可

**本文结构：** 接入原则与约定 → 步骤 1–7 → 测试。

接入原则
--------

- **复用 RPent 公共抽象。** Env、VLA、运行时和 Memory 优先复用已有组件，例如 ``BaseEnvClient``、``BaseEnvFacade``、``BaseVLAClient``、 ``BaseVLAFacade`` 和 ``MemoryManager``。
- **优先复用 RLinf 的 Env 或 VLA。** 如果 RLinf 已有对应实现，RPent 尽量只增加必要的适配层。
- **尽量和现有机器人接入方式保持一致。** ``RobotSpec``、Prompt、Toolkit 和运行时尽量参考已有实现，不为单个机器人引入新的公共机制。
- **无法复用时说明原因。** 如果 RPent 或 RLinf 已有相关 Env / VLA 但无法复用，请在 PR 描述中说明或提交 issue，帮助改进现有抽象。

建议遵循的约定
--------------

- ``output_dir`` 是 runner 为单次运行创建的工作目录。环境观测由 ``EnvState`` 管理；调用方只使用逻辑基础文件名，不自行拼接存储路径。 transcript 等运行管理输出与环境工件共享该目录。
- 工具提供 ``name``、``description`` 和 ``input_schema``，由各 planner 转换成对应模型接口的格式。
- 环境侧的返回值必须可 pickle，且不包含 torch 对象。
- 每个原语工具执行后要 dump 一次新的状态快照, 这样下一次 ``view_env_state`` 看到的是动作后的世界。
- ``dump_state`` 是 Agent 获取环境状态的唯一数据来源；任何新的模态（例如触觉、力）都通过它提供。

接入步骤概览
------------

RPent 的整体进程划分、服务职责和通信方式见 :doc:`系统说明 <architecture>`。接入机器人或仿真环境时，按以下顺序实现扩展点：

1. 在 :ref:`入口 <add-robot-entry>` 中注册 ``RobotSpec`` 和 toolkit 工厂。
2. 实现 :ref:`env_client 和 env_server <add-robot-env-rpc>`。如需接入 VLA 服务和 model client，参见
   :ref:`添加一个 VLA（或其他基于模型的原语）<add-primitive-model-based>`。
3. :ref:`定义 prompt <add-robot-prompts>`。
4. :ref:`实现 toolkit 和 primitives <add-robot-toolkit>`。
5. :ref:`注册环境参数并生成 RunConfig <add-robot-config>`。
6. 实现 :ref:`runtime 钩子 <add-robot-runtime>`：同一个钩子既能为普通 CLI 初始化完整 runtime，也能为 Dashboard 初始化指定的 component 子集。
7. 补充 :ref:`环境、各组件和完整调用链的测试 <add-robot-testing>`。

.. _add-robot-entry:

1. 入口与注册
--------------

新增名为 ``myrobot`` 的机器人时，目录结构如下：

.. code-block:: text

   robots/myrobot/
       __init__.py            # 包入口，仅重导出两个工厂
       robot_spec.py          # RobotSpec、工厂、Dashboard 描述和 runtime 钩子
       env_client.py          # MyEnvClient —— agent 侧 RPC client (步骤 2)
       prompt_bundle.py       # system()/user() prompt 工厂              (步骤 3)
       toolkit.py             # MyRobotToolkit + primitives + 工具定义     (步骤 4)
       env_server.py          # 环境侧 facade + RPC 服务                 (步骤 2)
       vla_server.py          # （可选）VLA 模型服务

``__init__.py`` 是机器人包入口，应保持精简，仅重导出 ``robot_spec.py`` 中实现的工厂。``rpent/robots/base.py`` 中的注册表会按需导入 ``robots.<name>``，并调用这两个函数：

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
       """向共享 parser 注册机器人参数。见第 4 节。"""
       ...

   def _parse_config(args) -> RunConfig:
       """校验最终的 args，返回 RunConfig。见第 4 节。"""
       ...

   def _init_runtime(
       args,
       output_dir,
       dashboard_events: DashboardEventSink,
       components: set[str] | None,
   ):
       """初始化全部 runtime components，或只初始化指定子集。

       返回 (daemons, runtime_kwargs)。见第 5 节。
       """
       ...

``resolve_dashboard`` 是可选回调；环境不支持 Dashboard 控制时保持为 ``None``。支持时，由回调返回机器人包中定义的配置：其中 ``task`` 描述命令、校验字段、展示模板和输出目录名称；机器人专用的会话设置仍通过普通命令行参数传入；``runtime_components`` 定义界面中的服务列表；``primitives`` 按顺序列出 Dashboard 展示并允许直接执行的 Toolkit 动作。相机标签页根据每步记录的 PNG 图像文件自动生成。任务候选项应直接保存在该配置中，避免导入机器人包时依赖仿真器包。完整结构参考 ``robots/libero/robot_spec.py``。

``_resolve_robot(name)`` 通过 ``importlib.import_module(f"robots.{name}")`` 动态加载机器人包。因此，只需将机器人包放在 ``robots/`` 下，无需维护中央注册列表。

``resolve_dashboard(args)`` 回调接收解析后的会话参数，可根据 ``--am-backend`` 等选项选择组件。固定布局直接返回静态配置即可，如上例所示。实体环境检查和 Dashboard 启动均调用此回调。

下文依次说明这些模块需要实现的内容。``_add_cli_args`` 和 ``_parse_config`` 见第 4 节，runtime 钩子见第 5 节。

.. _add-robot-env-rpc:

2. 环境 client 与 server
------------------------

这两个文件连接 agent 进程与 ``env_server``。client 在 agent 进程内将方法调用转换成 RPC 请求，``env_server`` 负责处理这些请求。

2.1 环境 client（agent 侧）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

继承 :class:`rpent.robots.components.env_client_base.BaseEnvClient`。它已经负责启动时校验 ``env.get_env_meta``、执行首次 reset、缓存 ``last_obs``，并实现公共的 ``reset``、``step``、``chunk_step``、``render_camera``、 ``get_camera_meta`` 和 ``get_task_language`` RPC。子类只需增加环境专用方法；扩展方法需要独立超时时，再扩展超时表。RPC 名称需要保持稳定，因为服务端 facade 会显式注册每个名称。

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

2.2 环境 server（环境侧）
~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``env_server`` 中定义与 client API 对应的 facade 类，例如 ``MyEnvFacade``。该类继承
:class:`rpent.robots.components.env_facade_base.BaseEnvFacade`；基类已提供公共 RPC 路由和
读写分派锁。子类实现公共环境方法，并通过 ``_register_rpc`` 增加环境专用路由。方法接收与 client 一致的位置参数和关键字参数，返回传输层支持的 Python / NumPy 值（不要返回 torch；agent 进程不导入 torch）。

.. code-block:: python

   from rpent.robots.components.env_facade_base import BaseEnvFacade

   class MyEnvFacade(BaseEnvFacade):
       def __init__(self, env, meta):
           self._env = env
           self._meta = meta
           super().__init__()

       def _register_rpc(self):
           super()._register_rpc()
           # 自定义方法需额外注册
           self._rpc["env.custom_method"] = self.custom_method

       # BaseEnvFacade 要求的抽象方法必须实现
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

``BaseEnvFacade`` 通过 ``_register_rpc`` 注册公共路由，并使用读写锁串行化会改变状态的调用。只有确认某个扩展路由可以安全地与其他读操作并发时，才把它加入 ``_readonly_methods``。继承的 ``RpcFacade.serve`` 负责绑定传输方式（HTTP 或 socket）、提供 ``healthz`` 和 ``shutdown``、检测父进程退出并执行资源清理。

.. _add-robot-prompts:

3. 提示词
---------

定义 ``system_prompt(variables)`` 和 ``user_prompt(variables)`` 两个 prompt 工厂，并在机器人的 ``robot_spec.py`` 中构造 ``PromptBundle(system=system_prompt, user=user_prompt)`` （见上面的“入口”）。每个工厂接收本次运行的 prompt 变量，返回 ``PromptNode``，通常是按调用顺序排列的 ``dict[str, PromptNode]`` 分节； ``PromptBundle.render`` 负责组装和填充。一套 prompt 供 API loop、Claude Code 和 Codex 等 planner 共用。正文使用工具的裸名（如 ``move_to``），并说明 Claude Code 和 Codex SDK 会将其显示为 ``mcp__rpent__<name>``；无需分别维护 CLI 与 API 版本。

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

将 prompt 内容保存在机器人包内，例如 ``robots/myrobot/prompts/system.py`` 和 ``user.py``。分节内容可以是普通字符串，也可以使用 ``BulletList`` 或 ``Numbered``。占位符 ``{{suite}}`` / ``{{task}}`` / ``{{seed}}`` / ``{{output_dir}}`` / ``{{recipe_tag}}`` 在渲染时填充。

.. _add-robot-toolkit:

4. 工具集与原语
----------------

该模块负责工具定义、动作原语、每步状态记录，以及允许通过 MCP 调用的工具列表。LIBERO 将这些内容分布在 ``tools.py`` 和 ``toolkit.py`` 中；新增机器人时，也可以将它们放在同一个 ``toolkit.py`` 中。

toolkit 模块通常包含四部分：

**Primitives 类**\ （例如 ``MyRobotPrimitives``）是 toolkit 持有的 Python 对象。它保存 ``EnvClient``、VLA ``model`` client 和单次运行所需的状态。每个原语工具（``move_to``、``pi0_pick``、``release`` 等）对应一个方法，并返回包含日志数据和可选 PNG 图片的 ``ToolResult``。

**工具定义和处理函数** 是使用 ``@tool`` 声明的函数或方法。参数类型注解和 Google 风格 docstring 提供 schema 与说明，包括 ``view_env_state``、``back_project`` 等读取工具。

**每步状态 dump** —— ``dump_state(primitives, env_state, log)`` 通过 ``env_state.record_step(...)`` 创建由 ``EnvState`` 持有的步骤，并取得分配的 step index；该 ``StepRecord`` 会被立即追加并提交。大型观测通过 ``env_state.save(...)`` 保存——在 ``record_step`` 块内可省略 ``step`` 参数（默认指向刚创建的步骤），传显式 ``step=<int>`` 可指定其它步骤，``step=None`` 用于运行级工件。每次保存成功后，``EnvState`` 会自动把基础文件名加入该 ``StepRecord`` 的扁平 ``artifacts`` 集合；读取方直接使用规范化的工件文件名。

**Toolkit 类** 继承 ``rpent.tools.toolkit.Toolkit``：

- 在 ``super().__init__(...)`` 中传入 ``memory`` （一个
  必需的 :class:`~rpent.memory.MemoryManager`）和 ``state``。``memory_access`` 和
  ``inbox_cell_tag`` 在构造 ``MemoryManager`` 时配置；eval 默认只读。
- 在 ``__init__`` 中通过自定义的初始化辅助方法构建 primitives（LIBERO 中的方法名为 ``init_primitives``；它会调用 ``EnvState.reset()``、构造原语并 dump 第 0 步）,
- 用 ``self.add_tools(iter_tools(self._primitives))`` 或 ``self.add_tool(definition)`` 注册绑定后的工具；通过 ``definition.with_handler(...)`` 绑定内部资源或执行检查，由 Toolkit 采集动作后的状态；
- 重写 ``close()``，通过 ``EnvState`` 保存 agent 侧剩余工件（例如 ``state.save("episode.mp4", frames, step=None)``）。

``runtime_kwargs`` 由 ``robot_spec.py:get_toolkit`` 转发给 toolkit，再原样传入 primitives 的 ``__init__``。其中通常包含 ``{"env": MyEnvClient(...), "model": VLAClient(...), ...}``。

5. 命令行参数与 RunConfig
-------------------------

用 ``_add_cli_args`` 注册机器人参数，并由 ``_parse_config`` 返回 ``RunConfig``。
钩子契约、校验规则和 ``RunConfig`` 字段见 :ref:`add-robot-config`。

6. Runtime 钩子
----------------

``init_runtime`` 启动或连接机器人服务，返回自有 daemon 和 toolkit 参数。
Dashboard 使用的 component 子集，以及启动与就绪等待辅助函数，见
:ref:`add-robot-runtime`。

.. _add-robot-testing:

7. 需要补充的测试
-----------------

新增机器人时，应先分别测试它使用的每个 runtime 组件，再跑一次完整调用链。每个组件都应实际调用一次并检查结果，仅能导入模块或通过服务健康检查还不够。

离线测试使用 ``pytest tests/unit_tests/robots/myrobot -v``；准备好 GPU、checkpoint 和资产后，使用 ``pytest tests/e2e_tests/myrobot -v``。各组件与完整调用链的测试要点见 :doc:`add_robot_reference`。
