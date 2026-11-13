机器人接入参考
==============

机器人接入的运行时钩子、启动流程与测试覆盖。接入步骤见 :doc:`add_robot`。

**本文结构：** 运行时钩子 → runtime 初始化 → 运行结果 finalizer → 测试要点。

.. _add-robot-config:

运行时钩子
------------------------------------------------------

机器人特有的 CLI 参数通过两个钩子接入 ``rpent/cli/main.py`` 的解析流程，并参与最终的 argparse 解析：

**``_add_cli_args(parser, use_dashboard) -> None``。** 将机器人参数注册到 main.py 已创建的共享 parser。``use_dashboard`` 决定原本必填的参数是否保持可选。每个 Dashboard TaskRun 会在 ``parse_config`` 调用前，由机器人 Dashboard spec 定义的任务命令提供其声明的字段。main.py 会在 ``parser.parse_args()`` 之前调用该钩子，因此 argparse 的 usage 和错误信息也会包含机器人参数。

**``_parse_config(args) -> RunConfig``。** 普通 CLI 模式下，该钩子在 ``parser.parse_args()`` 后调用；Dashboard 模式下，每个 TaskRun 会先把请求字段写入任务参数，再调用该钩子。该钩子校验这些字段并返回
:class:`~rpent.robots.RunConfig`：

- ``recipe_tag`` —— 单次运行的机器人标签，用于 transcript 文件名和 recipe 路径（LIBERO 使用 ``f"{suite.replace('libero_', '')}_t{task}_s{seed}"``）。
- ``output_dir`` —— 单次运行的临时目录路径。main.py 随后调用 ``init_output_dir`` 创建目录并配置日志。
- ``prompt_vars`` —— 传给 ``PromptBundle.render`` 的字典，通常包含运行标识和 prompt 引用的其他变量。
- ``task_desc`` —— 机器人特定的任务标识字典，会原样写入 transcript JSON 记录（LIBERO 使用 ``{"suite": ..., "task": ..., "seed": ...}``）。

.. code-block:: python

   def _add_cli_args(parser, use_dashboard) -> None:
       required = not use_dashboard
       parser.add_argument("--suite", default=None, required=required)
       parser.add_argument("--task", type=int, default=None, required=required)
       # ... 其他机器人参数 ...

   def _parse_config(args) -> RunConfig:
       if not args.suite: raise ValueError("--suite is required")
       # ... 生成 recipe_tag、output_dir 和 prompt_vars ...
       return RunConfig(
           recipe_tag=recipe_tag,
           output_dir=output_dir,
           prompt_vars=prompt_vars,
           task_desc={"suite": args.suite, "task": args.task, "seed": args.seed},
       )

.. _add-robot-runtime:

Runtime 初始化
---------------------

``init_runtime`` 返回 ``(owned_daemons, runtime_kwargs)``：

- ``owned_daemons: list[ProcessDaemon]`` 只包含当前进程实际启动的子进程，当前 runner 会在清理阶段停止它们。连接外部 endpoint 时，不能把外部服务加入该列表。
- ``runtime_kwargs: dict`` 会传给 toolkit 构造器，再由后者传入 primitives 的 ``__init__``。完整参数通常包含 ``{"env": MyEnvClient(...), "model": VLAClient(...)}``，以及其他辅助 client。

第四个参数 ``components`` 指定要初始化的服务名称。``None`` 表示全部服务，普通 CLI 会传入这个值。Dashboard 根据 ``dashboard.runtime_components`` 得到两个子集，每个 component 都必须显式声明 ``scope: "shared"`` 或 ``scope: "unique"``。Dashboard 先初始化一次 shared components，再为每个新的环境实例初始化 unique components。两次都调用同一个钩子，最后合并返回的 ``runtime_kwargs``。在 LIBERO 中，这两个子集分别是 ``{"vla", "sam3"}`` 和 ``{"env"}``。

实现应在启动任何服务前拒绝未知 component 名称。如果多个选中的本地服务初始化较慢，应先全部启动，再依次等待 ready，让初始化过程可以重叠。参考实现见 ``robots/libero/robot_spec.py`` 中的有序 component registry。

endpoint（``--env-endpoint``、``--am-endpoint``，以及 LIBERO 的 ``--sam3-endpoint``）解析和环境专用服务命令，应放在拥有对应服务的钩子中。这些 spawner 应通过 ``rpent.robots.runtime.try_spawn_server`` 和 ``try_wait_server`` 组合，使各环境的状态事件、就绪失败和 owned daemon 清理保持一致；runner 不处理这些环境细节。参考模式见 ``robots/libero/robot_spec.py`` 和 ``robots/robocasa/robot_spec.py``。

可选的运行结果 finalizer
------------------------

``RobotSpec.finalize_run`` 是面向所有机器人、与具体 benchmark 无关的通用运行结束钩子。RoboCasa、RoboDojo 和 YAM 注册它来记录单 cell 评测结果，供后续结果统计和聚合。任何需要发布机器可读评测产物的机器人都可以注册该钩子。其默认值为 ``None``，不会改变 runner 行为。配置该钩子后，普通终端 runner 和 Dashboard 都会在关闭 toolkit 前读取 ``toolkit.solved()``，完成运行时清理后再把结构化的 ``RunFinalizationContext`` 传给钩子。产物 schema 与文件名由钩子负责，RPent 只定义生命周期边界。

JSON 产物应使用 ``write_json_atomic``，避免中断写入留下不完整结果：

.. code-block:: python

   from rpent.evaluation import RunFinalizationContext, write_json_atomic

   def _finalize_run(context: RunFinalizationContext):
       return write_json_atomic(
           context.output_dir / "result.json",
           {
               "robot": context.robot_name,
               "task": dict(context.task_desc),
               "success": context.environment_success,
           },
       )

通过 ``RobotSpec(..., finalize_run=_finalize_run)`` 注册回调。普通终端运行和 Dashboard 都会调用该钩子。benchmark manifest、机器人专用 runtime 字段和聚合逻辑应继续放在机器人目录中，而不是共享 CLI。

测试要点
--------

测试放在哪里
~~~~~~~~~~~~

以下 ``myrobot`` 替换为新机器人的包名：

- ``tests/unit_tests/robots/myrobot/``：离线单元测试，覆盖配置解析、client 参数处理、工具分派，以及 runtime 启动和清理逻辑。用 fake 替代仿真器和模型，保证可在 CPU 上运行。
- ``tests/e2e_tests/myrobot/test_components.py``：为每个真实组件分别编写测试，例如 ``test_environment_component``、``test_pi05_component`` 和 ``test_sam3_component``；只需覆盖该机器人实际使用的组件。
- ``tests/e2e_tests/myrobot/test_policy_chain.py``：编写一个串起 planner、 toolkit、模型和环境的完整调用链测试。
- Fixture 放在同目录的 ``conftest.py``，可复用的场景初始化和调用放在 ``scenario.py``。生命周期与断言辅助函数复用 ``tests/e2e_tests/common.py``，目录组织可参考 ``tests/e2e_tests/libero/``。

每个组件测什么
~~~~~~~~~~~~~~

- **Env：** 启动真实环境，用固定 task/seed 执行 reset 并获取观测，检查所需相机图像和状态字段的 shape、dtype。至少执行一个合法动作，再检查下一帧观测、终止信息和成功判定。
- **VLA 或其他动作模型：** 加载真实 checkpoint，按该机器人的输入格式传入观测和指令，执行一次推理。检查返回动作非空、数值有限，且维度符合环境要求。
- **感知或其他服务：** 用已知输入实际调用每个服务，并验证输出。例如让 SAM3 分割图像中的已知物体，检查 mask 尺寸与图像一致且包含前景。

通过受支持的 runtime 接口启动各组件，并检查测试结束后自己启动的 daemon 全部退出。复用已有组件时可以复用其测试，但要说明已有覆盖位置，并补测新增的输入输出适配。

完整调用链测什么
~~~~~~~~~~~~~~~~

组件测试通过后，复用 ``tests/e2e_tests/common.py`` 中的 ``run_scripted_policy_chain``，以固定 task/seed 和有限动作数运行公开 CLI。其中的本地 ``OfflinePlannerServer`` 会请求一个真实动作原语，再调用 ``finish``，无需外部 LLM API。环境和模型服务保持真实，不要 monkeypatch CLI 或 runtime 内部实现。

检查至少执行了一个环境动作、transcript 记录了 ``finish``、``states.json`` 包含无错误的动作记录、生成了预期观测工件，以及自己启动的 daemon 全部退出。这种有界接入测试不要求任务成功。

离线测试使用 ``pytest tests/unit_tests/robots/myrobot -v`` 运行。安装机器人 extra 并准备好所需 GPU、checkpoint 和资产后，使用 ``pytest tests/e2e_tests/myrobot -v`` 运行真实组件和调用链测试。干净环境下的 GPU 套件运行方式见 ``tests/README.md`` 和 ``tests/e2e_tests/run_gpu_suite.sh``。
