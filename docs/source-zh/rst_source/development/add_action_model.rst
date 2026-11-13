添加动作模型
================

接入 VLA 或 WAM 服务，并将预测结果交给平台的原生动作执行器。工具声明与状态采集见 :doc:`add_primitive`，平台发现和运行时接线见 :doc:`add_robot`。

.. page-head::
   :for: 要接入 VLA 或 WAM 服务的开发者
   :outcome: 把模型服务接到平台的动作执行器，并验证整条调用链
   :read-when: 新增或替换动作模型时
   :skip-when: 只需要工具声明；见 :doc:`add_primitive`

**本文结构：** 共享架构 → 添加 VLA → 添加 WAM → 测试。

共享架构
--------

RPent 负责 agent 编排、平台观测与动作的语义映射，以及模型服务的连接。对于 RLinf 已支持的模型与平台组合，接入代码复用其模型加载、推理和数据转换。其余组合由模型包连接模型的原生实现，并补充所需的数据转换。

VLA 和 WAM 通过公共 AM 基类复用 RPC 注册与推理转发。VLA 保留现有的模型专用消息格式和推理路径；WAM 使用 ``am_contracts.py`` 中的物理观测与原生控制声明，连接平台客户端和模型适配器。

``am_runtime.add_am_args(parser, platform=...)`` 统一注册当前平台支持的后端与公共部署参数。GPU 选择和兼容别名见 :doc:`../guides/cli`。

下面以 WAM 执行链路说明平台与模型之间的职责边界：

.. code-block:: text

   CLI / Dashboard
     -> robots/<platform>/robot_spec.py: configuration and service startup
     -> toolkit.py: register platform tools
     -> wam_act: observe, predict, execute, record
     -> observation.py + wam_client.py: physical observations and control identity
     -> BaseWAMClient -> existing HTTP/socket RPC -> BaseWAMFacade
     -> <model>/adapter/encode.py -> predict_native -> adapter/decode.py
     -> action chunk -> platform env_client.chunk_step -> simulator

``wam_act`` 在 LIBERO 的 ``tools.py`` 和 RoboTwin 的 ``primitives.py`` 中通过 ``@tool`` 声明，返回 ``ToolResult(data=...)``。平台已有 toolkit 负责工具注册、取消、状态采集和录制。

.. list-table:: 文件职责
   :header-rows: 1

   * - 位置
     - 职责
   * - ``robots/<platform>/observation.py``
     - 提取具名物理传感器与状态，不做模型归一化。
   * - ``robots/<platform>/control.py``
     - 定义原生动作的字段顺序、含义和执行模式。
   * - ``robots/<platform>/wam_client.py``
     - 选择兼容控制方式，给物理观测附加执行身份。
   * - ``rpent/robots/components/am_contracts.py``
     - 分节声明共享物理观测、原生控制，以及 WAM 专用的能力、请求和结果字典。
   * - ``am_client_base.py``
     - 定义公共 ``BaseAMClient`` 及 VLA/WAM 子类，共享推理转发和超时处理，各自保留协议参数与检查。
   * - ``am_facade_base.py``
     - 通过 ``BaseAMFacade`` 共享推理路由、可选的模型元数据查询和 RPC 会话初始化；子类分别负责 VLA/WAM 行为。
   * - ``am_runtime.py``
     - 统一注册公共部署参数，将 VLA/WAM 配置解析为 ``AMConfig``，按指定 Python、工作目录和 GPU 启动 worker。
   * - ``rpent/robots/components/pi05_vla_client.py``
     - 为 Pi0.5 适配平台观测和模型输出；其他 VLA 接入提供各自的模型客户端。
   * - ``<model>/runtime_config.py``
     - 补充 WAM 模型专属参数、默认值和配置要求。
   * - ``<model>/server.py``
     - 加载 WAM 模型或连接其原生服务，实现推理调用。
   * - ``<model>/adapter/{__init__,encode,decode}.py``
     - 注册成对转换，构造模型输入并还原平台动作。

物理观测可由 VLA 和 WAM 复用，模型编码仍由各自 adapter 实现。例如 Cosmos 将 LIBERO 的 xyzw 四元数拼入 9 维状态，Fast-WAM 则转换成轴角后组成 8 维状态。RoboTwin 分开提供控制器关节目标与实测关节位置；Fast-WAM 使用对应原生 ``joint_action.vector`` 的目标值。

平台 ``robot_spec.py`` 通过回调连接各层启动逻辑。WAM worker 的调用链如下：

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

VLA 启动函数也使用 ``AMConfig.spawn_worker()``。平台保留各自的服务命令和传输方式，包括 LingBot 的原生 WebSocket 连接与 RoboCasa 的带会话 RPC。``ProcessDaemon`` 在启动失败时关闭日志；公共 ``rpent/robots/runtime.py`` 在资源交接后负责等待就绪、组件状态和进程组清理。连接外部 endpoint 时不返回自有 daemon。

``AMConfig`` 保存解析后的后端、平台、endpoint、checkpoint、Python、工作目录、GPU 和额外的 worker 参数。默认值解析不会修改原始 Namespace，避免 Dashboard 再次使用时把默认值误认为显式参数。WAM 的 ``runtime_config.py`` 补充模型专属默认值和 worker 参数；VLA 平台启动函数保留各自的原生命令构造。

添加 VLA
--------

由于模型运行在独立进程中，添加基于模型的原语还需要以下组件：

1. **编写 ``vla_server.py``。** 该进程只持有模型权重和 CUDA 上下文。继承 :class:`rpent.robots.components.am_facade_base.BaseVLAFacade`，实现 ``predict``，并通过扩展 ``_register_rpc`` 注册其他模型 RPC：

   - 默认传输方式为 **HTTP**，通过 ``POST /call`` 传输 JSON，适合
     LIBERO/Pi0.5 使用的扁平 ``image + state`` 数据。
   - 当观测数据包含多帧历史信息或采用嵌套数据结构时，可以切换到
     **socket RPC**\ （``--transport socket``），避免重复进行 JSON 编码。

   ``BaseVLAFacade`` 会注册 ``vla.predict`` 并串行化模型调用。构造时传入 ``model_meta=...`` 还会注册只读的 ``vla.get_model_meta`` 路由，元数据字段由具体模型定义。继承的 ``RpcFacade.serve`` 负责绑定传输层、处理 ``healthz`` 和 ``shutdown``、检测父进程退出并清理资源。

2. **编写 model client。** 继承
   :class:`rpent.robots.components.am_client_base.BaseVLAClient`；它已经提供
   公共的 ``vla.predict`` 调用，子类只需增加环境专用的输入 / 输出适配。 LIBERO 的实现可参考 ``rpent.robots.components.pi05_vla_client.Pi05VLAClient``。

3. **在 primitives 中添加方法。** 在当前机器人的 primitives 类中调用 model client，将其返回的动作块交给环境执行，并返回 ``ToolResult``。 model client 的接口是
   :meth:`rpent.robots.components.pi05_vla_client.Pi05VLAClient.predict`，
   指令从 ``env_obs["task_descriptions"]`` 中读取；返回形状为 ``[chunk, action_dim]`` 的 NumPy 动作块（已移除 batch 维度）：

   .. code-block:: python

      @tool
      def mymodel_pick(self, target: str) -> ToolResult:
          """使用模型抓取指定目标。"""
          env_obs = self._env.get_obs()
          env_obs["task_descriptions"] = f"pick {target}"
          chunk = self._model.predict(env_obs)
          self._env.chunk_step(chunk)
          return ToolResult(data={"model": "mymodel", "target": target})

4. **在 toolkit 中注册声明的工具。** 具体做法与脚本化原语相同。

5. **在 ``robot_spec.py`` 中连接各组件。** 机器人的 ``get_toolkit`` 使用 ``runtime_kwargs`` 构造 toolkit：

   .. code-block:: python

      def get_toolkit(*, runtime_kwargs, dashboard_events, config):
          from robots.myrobot.toolkit import MyRobotToolkit
          from rpent.memory import MemoryManager

          return MyRobotToolkit(
              runtime_kwargs=runtime_kwargs,
              dashboard_events=dashboard_events,
              memory=MemoryManager(config.prompt_vars["memory_dir"]),
          )

   机器人包中的 ``_init_runtime`` 则负责构造 ``runtime_kwargs``，例如 ``{"env": MyRobotEnvClient(...), "model": MyModelClient(...)}``，再由 toolkit 构造器将其转发给 primitives。

已有服务的部署方式与 endpoint 示例见 :doc:`../guides/advanced_deployment`。有状态模型还需要实现 :doc:`action_model_reference` 中的按客户端隔离与重置逻辑。

添加 WAM
--------

Cosmos Policy 和 Cosmos3 支持 LIBERO、LIBERO-PRO。Fast-WAM 支持 LIBERO、LIBERO-PRO 和 RoboTwin。每个模型与平台组合都需要匹配的 checkpoint。

``cosmos-policy`` 使用 NVIDIA 发布的 ``Cosmos-Policy-LIBERO-Predict2-2B`` 权重和官方 LIBERO 推理接口。``cosmos3`` 通过 RLinf 的 ``Cosmos3SGLangAdapter`` 和 HTTP client，连接独立部署的 SGLang ``/v1/actions/generations`` 服务。图像拼接、请求构造、动作反归一化和旋转转换由 RLinf 负责，其 ``prepare_actions_for_libero`` 还负责适配仿真器的夹爪约定。RPent 复用已有 LIBERO client，只在接口边界映射观测与预测。这两个后端需要不同的 checkpoint。

1. 在 ``rpent/robots/components/`` 下创建模型包。``server.py`` 继承 ``BaseWAMFacade`` 并实现 ``predict_native``，必须提供 ``(encode, decode)`` adapter 函数对。
2. 使用 ``am_facade_base.py`` 中的 ``WAMAdapterSpec`` 在模型的 ``ADAPTERS`` 中注册支持的平台。模型元数据工厂声明 checkpoint 身份、相机与状态要求、原生控制约定及可执行 chunk 长度。encode 将物理观测转换为模型输入，decode 将预测还原为声明的平台动作格式。
3. 观测和控制契约匹配时，复用平台的 ``wam_client.py``。``BaseWAMClient`` 在初始化时调用一次 ``wam.get_model_meta``，将结果保存在 ``model_meta``；平台在执行预测前检查控制兼容性。
4. 在 ``runtime_config.py`` 中补充部署参数，并在 ``am_runtime.WAM_BACKENDS`` 注册后端；模型专属启动逻辑留在模型包内。在模型包中声明是否使用会话；推理保留会话历史时实现 ``reset_native``。
5. 在平台运行时与工具执行中接入所选后端。回合边界重置模型历史，结束后关闭客户端。每个 toolkit 都必须持有 ``MemoryManager``。

WAM 的通信协议、生命周期和平台检查清单见 :doc:`action_model_reference`；独立 worker 与随运行启动的部署方式也在该页。

.. _wam-protocol:

测试
----

新增模型与平台组合时，扩展已有的适配器、RPC 和平台测试。测试位置、GPU 环境要求、运行命令，以及集成检查与任务成功率评测的区别，统一见 ``tests/README.md``。
