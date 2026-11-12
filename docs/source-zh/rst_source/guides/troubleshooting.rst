问题排查
========

先看 ``run.log`` 中最先出现的错误，后面的报错通常由它引起。服务启动失败的信息写在输出目录的 ``*_server.log`` 中，规划器消息保存在 ``transcript_*.json``。

常见问题
--------

.. list-table::
   :header-rows: 1
   :widths: 28 44 28

   * - 现象
     - 检查
     - 详见
   * - ``rpent: command not found``
     - 激活安装 RPent 的 Python 环境，例如 ``source .venv/bin/activate``。
     - :doc:`../get_started/quickstart`
   * - 启动时仿真器或模型导入失败
     - 安装对应 extra（``.[libero]``、``.[libero-pro]``、``.[robocasa]`` 等）。同一环境只装一个 LIBERO 变体。
     - :doc:`../simulators/index`
   * - 服务启动时报 CUDA 或驱动错误
     - 安装与驱动匹配的 PyTorch 版本，再运行该环境的检查命令。
     - :doc:`../simulators/libero`、:doc:`../simulators/robocasa`
   * - 显存不足
     - 检查 GPU 上的其他进程；支持的平台可用 ``--env-cuda-device`` 和 ``--am-cuda-device`` 分开分配设备。
     - :doc:`../simulators/robotwin`
   * - 服务在第一次工具调用前退出
     - 查看输出目录中的 ``env_server.log``、``vla_server.log`` 或 ``sam3_server.log``，其中记录失败组件。
     - :ref:`run-output-files`
   * - 模型或资源下载失败
     - 需要授权的权重先申请访问并执行 ``hf auth login``；可设置 ``HF_ENDPOINT`` 使用镜像，或按页面给出的 ModelScope 命令下载。
     - :doc:`../get_started/quickstart`
   * - 规划器检查失败
     - 用相同的 ``--planner`` 和 ``--model`` 运行 ``rpent-check-llm``；错误类别可区分配置、认证、模型和网络问题。
     - :ref:`planner-check`
   * - 规划器能连接，但任务全部失败
     - 先确认 checkpoint 路径和原生成功判定，查看录像和最终状态，再调整规划器设置。
     - :ref:`leaderboard-protocol`
   * - 外部服务连接不上
     - 传入 ``host:port`` 形式的端点，而不是只写端口；服务需在另一终端或节点保持运行。
     - :doc:`advanced_deployment`
   * - 记忆缓存被拒绝使用
     - 删除版本缓存中的多余文件，或联网重新同步。``HF_HUB_OFFLINE=1`` 要求缓存完整且未改动。
     - :doc:`memory`
   * - Flash 找不到计划
     - 该任务可能没有成功的源计划；Astra memory 也没有重放资源。Flash 应使用 GPT-5.5 memory。
     - :doc:`flash`
   * - 其他机器打不开 Dashboard
     - 默认只监听 ``127.0.0.1``，请使用 SSH 端口转发。
     - :doc:`advanced_deployment`
   * - 真机运行无法启动
     - 按对应机器人页面检查标定和姿态前提；环境服务会在启动前校验。
     - :doc:`../real_world_robots/index`

提供排查信息
------------

报告问题时，请附上运行的命令、``run.log`` 中的首个错误、相关服务日志和输出目录结构；不要包含 API key 或凭据。任务失败不一定框架有问题：请先把最终环境状态与环境页的成功标准对照。
