YAM
===

RPent 通过 RLinf 的 real-world YAM 运行时（i2rt）控制一台双臂 YAM 机械臂，
并读取三路 RealSense RGBD 相机。控制机是唯一的 CAN 写入方，Agent 机只通过
RPC 观察并下发原语。

安装
----

YAM 复用 RLinf 的 real-world 运行时和 i2rt SDK，RPent 侧没有单独的 extra：

.. code-block:: bash

   uv sync --extra rlinf

控制机还需要 RealSense 绑定（``pyrealsense2``），以及一份包含 i2rt 和 YAM
后端的 RLinf 检出。RPent 通过 ``RPENT_RLINF_ROOT``（或 ``RLINF_REPO_PATH``）
定位该检出，详见 :doc:`advanced_deployment`。

.. note::

   安装只解决 Python 依赖，不构建 CAN 与电机控制栈。接管前必须由现场人员
   确认：四臂支撑稳定、可急停、工作区和允许范围明确，其他数采/遥操程序已
   正常退出，且全程不重启。

现场配置
--------

``robots/yam/config/example.yaml`` 是整机的唯一配置，包含机器身份（follower
CAN 通道、三路相机序列号、手眼外参、桌面几何）、原语控制参数和操作员回执
路径。复制成现场配置后逐项替换：

* ``robot.*.channel`` 必须是内核 SocketCAN 接口名（``ip link`` 中的
  ``can0``/``can1``），不是逻辑别名。
* ``cameras`` 固定 640×480@30，序列号必须与现场相机一致。
* ``extrinsics_path`` 指向手眼标定产出的 JSON；为 ``null`` 时禁用依赖腕部
  相机的世界坐标投影。
* ``table_z``（水平桌面）与 ``table_surface``（有限倾斜桌面）二选一，用于
  桌面净空检查。两者都不配置时，所有原语运动都会被拒绝，只允许观察。
* ``operator_receipt_path`` 是操作员写 ready/success/failure/abort 回执的
  本地文件；不配置则拒绝启动。

任务名、任务语言、seed 和 step 预算都是命令行参数，必须与 Agent 侧完全一致；
把它们写进 YAML 是错误而不是覆盖。``control:`` section 中的安全/健壮性参数
（slew、超时、相机预热、桌面余量、路径步长、静止容差）可以现场重调，文件里
的值是打包默认值，代码中没有第二份副本。

启动环境服务
------------

env server 独占 CAN 与相机，必须在 Agent 之前启动，并与其他 CAN 程序
（数采、遥操、hover 工具）互斥运行：

.. code-block:: bash

   export RPENT_RLINF_ROOT=/path/to/RLinf
   python -m robots.yam.env_server \
     --robot-config /path/to/site.yaml \
     --task-name tabletop_cleanup --task-language '把桌面上的方块放进目标容器' \
     --seed 0 --max-episode-steps 12000 \
     --transport http --host 127.0.0.1 --port 8110

``healthz`` 和静态 metadata 不会打开硬件；第一次 observe/reset/render 才会
打开三路相机、连接电机并输出保持扭矩。``gripper_limits: null`` 会触发夹爪
寻两端标定，必须保证夹爪无物且运动空间清楚。服务退出可能释放扭矩，退出前
必须支撑四臂。

运行 Agent
----------

用与 env server 完全相同的 task/seed/step 预算启动 Agent：

.. code-block:: bash

   export RPENT_RLINF_ROOT=/path/to/RLinf
   python -m rpent.cli.main --robot yam --planner codex \
     --task-name tabletop_cleanup --task-language '把桌面上的方块放进目标容器' \
     --seed 0 --max-episode-steps 12000 \
     --env-endpoint http://127.0.0.1:8110 --without-vla \
     --memory-profile local --memory-dir /path/to/memory/yam

YAM 默认使用本地 memory（``default_memory_profile="local"``），不会隐式同步
远程 corpus。``--without-vla`` 表示只用几何原语：``pi05_act`` 不会注册，
提示词也会明确它不可调用。传入 ``--vla-endpoint`` 后 ``pi05_act`` 才可用；
真机上请保持短块。

人工回执
--------

物理场景恢复和成功裁决都由现场操作员完成，RPent 不自动复位、不清错、不重新
使能。首回合先用 ``status`` 取得 episode ID，再由现场确认写 ``start``：

.. code-block:: bash

   python -m robots.yam.operator_control --robot-config /path/to/site.yaml \
     --event status
   python -m robots.yam.operator_control --robot-config /path/to/site.yaml \
     --event start --episode-id ACTUAL_EPISODE_ID --note '现场已确认摆场和允许范围'

``status`` 会调用 observe，必须在接管确认后使用。Explore 需要人工恢复场景时，
实际操作完成后写 ``--event ready``，由 Agent 的 reset 消费该回执；不能根据等待
时长、Agent 声明或脚本成功写 ready/success。最终 ``success``/``failure``/
``abort`` 同样必须来自真实现场反馈，并绑定当前 episode ID。

探索（Explore）
---------------

在同一命令上追加：

.. code-block:: bash

   --explore --explore-sessions 1 --explore-attempts-per-session 3

Explore 沿用 LIBERO 的组织方式：独立的 planner sessions、每 session 尝试预算、
失败归因与成功 recipe 归纳。真机 reset 只消费操作员 ready 回执并更新 episode
ID，不重建物理场景。

记忆与裁决
----------

Explore 草稿写在 ``memory/yam/_internal/inbox/<tag>/``，成功 recipe 按公共
MemoryManager 机制发布。工具的局部 ``success=True`` 只表示原语执行完成，不能
发布成功任务记忆；只有当前 episode 的人工成功证据可以生成成功 recipe。失败
audit 保留，不冒充已验证技能。

每次运行检查 ``result.json`` 的 ``environment_success``。``planner_finish_request``
只是 Agent 的声明，不能单独据其 success 字段判定真机成功。

工具与状态产物
--------------

YAM 提供 ``view_env_state``、``sample_world_xyz``、``query_world_map``、
``render``、``move_to``、``rotate_wrist``、``set_gripper``、``release`` 和
``finish``；连接 VLA 后额外提供 ``pi05_act``，探索模式额外提供 ``reset``。

状态和动作布局是绝对 ``qpos14``：
``[left_q0..q5, left_gripper, right_q0..q5, right_gripper]``，关节单位为 rad，
夹爪 ``0=闭、1=开``。三视角为 ``top``、``left``、``right``，后两者是腕相机。
所有 xyz 目标都在 ``left_base`` 世界系下，单位为米，姿态四元数为 wxyz。

每次 observe 返回一个快照，绑定三视角 RGB、对齐深度、内参、CV cam2world、
图像设备时间和关节测量时间。三路相机没有硬件同步，host 到达时间也不等于曝光
时间。``sample_world_xyz`` 和 ``query_world_map`` 读取同一帧的持久化深度投影；
帧过期或投影无效时返回无效点，不会默默当成桌面目标。

安全要求
--------

操作员必须守在硬件急停旁。软件 stop 只置事件，由执行循环在下一边界 hold，
ACK 不等于物理急停。桌面检查只覆盖采样 TCP 的净空，不是碰撞规划：连杆、自碰、
双臂互撞、夹持物、纸袋和碗都不在模型里。每次抓、提、放后都必须重新观察；
原语执行成功不能替代物体状态验证。

``enable_auto_recovery=false`` 表示运行中不会自动清错或重新使能，清错与重新
使能必须由现场人员在启动阶段完成。RPent 按 CAN 通道加进程锁并检查现存
SocketCAN 订阅，但其他程序不共享该锁，仍需现场保证排他。
