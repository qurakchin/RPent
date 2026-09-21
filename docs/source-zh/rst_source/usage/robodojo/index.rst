RoboDojo
========

RoboDojo 是 RPent 的一个可插拔仿真后端（``rpent --robot robodojo``），把
Isaac Sim / IsaacLab 上的双臂 ARX-X5 与 Pi_05 策略接入 RPent 的
LLM-in-the-loop runner，与 LIBERO 等后端并存。Planner（LLM）、工具协议、
SAM3 感知与 memory 层完全复用，只替换"身体"（仿真器/机器人）。

主要模块
--------

* ``robots/robodojo/env_server.py`` —— Isaac Sim RPC 服务（主线程渲染、
  三相机 + 深度 + 标定、joint/ee 动作、逐相机视频录制）。
* ``robots/robodojo/env_client.py`` —— 继承 ``BaseEnvClient`` 的 rpent
  侧客户端。
* Pi0.5 策略走共享的、与 env 无关的
  ``rpent/robots/components/pi05_vla_server.py`` 与其客户端
  ``rpent/robots/components/pi05_vla_client.py``。RoboDojo 选择
  ``robodojo`` embodiment（``--embodiment robodojo``）：服务端映射到
  ``pi05_robodojo_arx_x5`` openpi 配置，客户端映射到
  ``_encode_obs_robodojo``（头部 + 两个腕部视图、14 维关节状态）。服务端
  通过 ``--model-path`` / ``PI05_CHECKPOINT_PATH`` 读取权重，通过
  ``--norm-stats-path`` / ``PI05_NORM_STATS_PATH`` 读取归一化统计。14 维
  关节动作的解码在 ``tools.py`` 的 ``pi0_pick``。本仓库没有 RoboDojo 本地
  的 ``vla_server.py`` / ``vla_client.py``。
* ``robots/robodojo/toolkit.py`` / ``tools.py`` —— view_env_state /
  back_project / segment / move_to / set_gripper / pi0_pick / stabilize /
  place_in_bin / get_reward_details 等原语。
* ``robots/robodojo/robot_spec.py`` —— RobotSpec 工厂（CLI、RunConfig、
  运行时编排）。
* ``robots/robodojo/tasks.py`` —— 只读任务清单。它 glob 工作区
  ``task/RoboDojo/config/`` 下的 ``*.yml`` 任务配置文件名（排除
  ``_task.yml``），而不是内嵌固定任务列表，因此可用任务随 RoboDojo
  checkout 变化。

快速开始
--------

.. code-block:: bash

   cd <rpent checkout>
   export PATH="<venv>/bin:$PATH" \
     ROBODOJO_WORKSPACE=<workspace> \
     PI05_CHECKPOINT_PATH=<转换后的 Pi0.5 checkpoint> \
     PI05_NORM_STATS_PATH=<含 norm_stats.json 的目录> \
     SAM3_CHECKPOINT_PATH=$PWD/checkpoints/sam3/sam3.pt \
     HF_HUB_DISABLE_XET=1 CELL_TIMEOUT_S=3600
   rpent --robot robodojo --task put_bottles_into_dustbin --layout 1 \
     --cuda-device 0 --planner codex --model deepseek-v4-flash --max-turns 30

选 GPU 的 flag 是 ``--cuda-device``（不是 ``--sim-device``），它同时作用于
Isaac Sim env 服务与 Pi0.5 VLA 服务。``--env robodojo`` 是
``--robot robodojo`` 的已弃用别名。

运行输出（含 reward_details 审计、三相机 mp4、transcript）写到
``logs/<timestamp>_robodojo_<task>_l<layout>/``。

从零搭建完整环境请见 :doc:`installation`；命令完整的"三运行时"指南
（editable IsaacLab、CuRobo、JAX→PyTorch checkpoint 转换与必需环境变量）
见 ``docs/ROBODOJO_INSTALLATION.md``；裸策略 vs Harness 的对照口径见
:doc:`ab_protocol`；集成过程记录见 :doc:`integration_log`。
