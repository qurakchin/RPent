问题排查
========

先看 ``run.log`` 中最先出现的错误，后面的报错通常由它引起。服务启动失败的信息写在输出目录的 ``*_server.log`` 中，规划器消息保存在 ``transcript_*.json``。

.. page-head::
   :for: 运行失败或结果不符合预期的读者
   :outcome: 定位首个错误、应用对应修复，并为问题报告收集证据
   :read-when: 命令报错，或运行结束但没有得到预期结果时
   :skip-when: 运行成功；继续看平台页面的结果章节

**本文结构：** 先看首个错误 → 按现象检查与修复 → 提供排查信息。

常见问题
--------

每一行给出检查方法、修复或确认原因的命令，以及需要重跑的步骤。重跑时请换用新的 ``--output-dir``，保留失败运行的日志和产物。

.. list-table::
   :header-rows: 1
   :widths: 18 22 45 15

   * - 现象
     - 检查
     - 修复与恢复
     - 详见
   * - 找不到 ``rpent`` 命令
     - 当前 Python 环境没有安装 RPent。
     - 执行 ``source .venv/bin/activate``，用 ``which rpent`` 确认后重跑原命令。
     - :doc:`../get_started/quickstart`
   * - 启动时仿真器或模型导入失败
     - 当前环境缺少对应 extra。
     - 安装对应 extra，例如 ``uv pip install -e ".[libero-pro]"``；同一环境只装一个 LIBERO 变体，然后重跑。
     - :doc:`../simulators/index`
   * - 服务启动时报 CUDA 或驱动错误
     - PyTorch 与驱动或 GPU 不匹配。
     - 用 ``python -c "import torch; print(torch.version.cuda, torch.cuda.is_available())"`` 检查；重装匹配的 PyTorch，然后重跑。
     - :doc:`../simulators/libero`、:doc:`../simulators/robocasa`
   * - 显存不足
     - 其他进程占用显存，或两个服务共用一张卡。
     - 用 ``nvidia-smi`` 检查并停止其他任务，再拆分设备：``--env-cuda-device 0 --am-cuda-device 1 --sam3-cuda-device 0``。
     - :doc:`cli`
   * - 服务在第一次工具调用前退出
     - 失败的服务已记录错误。
     - 查看 ``tail -n 50 <输出目录>/env_server.log``（以及 ``vla_server.log``、``sam3_server.log``）；修掉首个错误，换新输出目录重跑。
     - :ref:`run-output-files`
   * - 模型或资源下载失败
     - 认证、镜像或磁盘空间。
     - 受限权重先执行 ``hf auth login``；镜像前缀为 ``HF_ENDPOINT=https://hf-mirror.com liberopro-download-assets --skip-existing``。重跑失败的步骤，``--skip-existing`` 会保留已完成文件。
     - :doc:`../get_started/quickstart`
   * - 规划器检查失败
     - 配置、认证、模型或网络错误。
     - 重跑 ``rpent-check-llm --planner claude_code --model claude-opus-4-8``；按报告的类别修复后重跑完整任务。
     - :ref:`planner-check`
   * - 规划器能连接，但任务全部失败
     - checkpoint 路径或原生成功判定。
     - 查看 ``view_env_state(step=-1)``，只有顶层 ``terminated`` 表示成功；修正 checkpoint 路径后重跑。
     - :ref:`leaderboard-protocol`
   * - 外部服务连接不上
     - 端点格式错误，或服务未运行。
     - 用 ``curl -s -X POST http://HOST:PORT/call -H 'Content-Type: application/json' -d '{"method":"healthz"}'`` 检查，应返回 ``{"status": "ok"}``；启动或转发服务后重跑。
     - :doc:`advanced_deployment`
   * - 记忆缓存被拒绝使用
     - 缓存有多余文件或不完整。
     - 删除多余文件，或联网重建：``python -m robots.libero.memory sync --memory-version GPT_6_astra_low``。``HF_HUB_OFFLINE=1`` 时缓存必须完整且未改动。
     - :doc:`memory`
   * - Flash 找不到计划
     - 所选记忆没有成功的源计划或重放资源。
     - 使用 ``--memory-version GPT_5.5_xhigh``，或包含 ``flash/`` 资源的本地 ``--memory-dir``，然后重跑。
     - :doc:`flash`
   * - 其他机器打不开 Dashboard
     - 默认只监听 ``127.0.0.1``。
     - 转发启动时打印的端口：``ssh -N -L 8000:127.0.0.1:8000 USER@HOST``，再打开 ``http://127.0.0.1:8000``。
     - :doc:`advanced_deployment`
   * - 规划器在回合上限处停止
     - ``--max-turns`` 的预算已用完，``api`` 后端还包括模型重试。
     - 到达上限属于正常停止，不代表任务失败。调高 ``--max-turns`` 或缩小任务范围后重跑。
     - :doc:`configure_planner`
   * - 真机运行无法启动
     - 标定、姿态前提或急停状态。
     - 完成机器人标定与姿态检查，松开急停，确认机械臂和夹爪状态后重跑。
     - :doc:`../real_world_robots/index`

提供排查信息
------------

报告问题时，请附上运行的命令、``run.log`` 中的首个错误、相关服务日志和输出目录结构；不要包含 API key 或凭据。任务失败不一定框架有问题：请先把最终环境状态与环境页的成功标准对照。
