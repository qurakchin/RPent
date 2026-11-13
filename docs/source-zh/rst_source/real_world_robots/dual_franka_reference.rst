双臂 Franka 参考
================

双臂部署的工具接口、探索模式与 Flash 回放。安装和首次运行见 :doc:`dual_franka`。

**Page map:** 工具与状态产物 → 探索模式 → Flash 回放。


工具与状态产物
--------------

双臂 Franka 扩展提供 ``view_env_state``、``view_camera_meta``、``describe_dual_franka_setup``、``back_project``、``segment``、``move_delta``、``rotate_delta``、``open_gripper``、``close_gripper``、``recover_joint_posture``、``vla_right_grasp`` / ``vla_handoff`` / ``vla_left_place``、``request_scene_reset`` 和 ``request_operator_verdict``。每次解析式运动只会作用于一条臂（``left`` 或 ``right``）。``back_project`` 和 ``segment`` 使用配置的度量相机视角；``segment`` 还需要 SAM3 客户端。``recover_joint_posture`` 会重新下发每个夹爪当前的张开/闭合状态，将双臂关节复位到 ``workspace.joint_reset_qpos``，默认还会将两个 TCP 移回恢复前的位置附近。所有会改变环境状态的工具都会在 RPent 统一的 ``EnvState`` 中保存每条臂的状态以及同步的 left-wrist、base 和 right-wrist 图像。

探索模式
--------

在任务运行命令后追加 ``--explore``，即可启用探索模式。``--explore-attempts-per-session`` 设置每个规划器会话的尝试次数，``--explore-sessions`` 设置会话数；终端交互再加 ``--tui``，网页交互改用 ``--dashboard``。

每个规划器会话先通过 ``request_scene_reset`` 请求场景确认。处理夹持物体、恢复场景后回复 ``done``；机器人复位成功并取得相机和状态观测后开始一次尝试，复位失败时不允许运动。``--explore-attempts-per-session`` 限制每个会话的尝试次数。普通任务和探索模式通过 ``--env-endpoint`` 接入的外部服务都必须声明 ``explicit_reset_only=True``。

``request_operator_verdict`` 请求 ``success``、``failure``、``continue`` 或 ``abort``，可附备注。其中 success/failure 答复判定当前尝试，``continue`` 继续尝试，``abort`` 停止探索。后续运动会清除先前判定；关闭终端输入也会停止探索。

使用 Codex/Claude 并加 ``--tui`` 时，确认回复使用显示的请求 ID，例如 ``/operator <request-id> done`` 或 ``/operator <request-id> success 物体已提起``；普通消息发送给智能体。不加 ``--tui`` 时直接按提示答复；使用 ``--dashboard`` 时在 Dashboard 消息输入框中输入下述命令。

日志与记忆
~~~~~~~~~~

``sessions/session_<NNN>/`` 保存相机和机器人状态，``exploration.json`` 记录尝试边界，``operator_events.json`` 记录人工反馈。失败尝试的记录会保留，工作笔记位于 ``<memory-dir>/_internal/inbox/<recipe_tag>/wip/``。

默认启用 memory 合并。正常结束后合并合法的 ``global`` / ``task-family`` 草稿，包括失败尝试的经验；成功时还将完整的 audit/recipe 文件对保存到 ``task-specific``。使用 ``--no-auto-merge-memory`` 可保留记录而不合并。运行错误、中止、切换任务或关闭 Dashboard 会话时不合并。记忆目录说明见 :doc:`../guides/memory`。

探索命令
~~~~~~~~

在 Codex/Claude 终端交互（``--explore --tui``）或 Dashboard 探索中，可使用：

* ``/success`` 或 ``/failure``：结束整个任务，而不只是判定当前尝试。成功要求场景已确认且复位成功；终端中可在首次复位前用 ``/failure`` 结束任务，Dashboard 中则需先用 ``/done`` 或 ``/abort`` 回答待处理的复位请求。
* ``/done``：确认待处理的场景复位请求。
* ``/continue``：回答待处理的判定请求并继续尝试。
* ``/abort``：停止任务，相机不可用时也可使用。

每条命令单独输入。不带斜杠的 ``success``、``failure`` 等词语是发给智能体的普通消息。已发送的机器人动作或 RPC 可能需返回后才能结束任务；这些命令不是急停。


Flash 回放
----------

双臂使用共享的 :ref:`Franka Flash 流程 <franka-flash>`。以下以任务 ``0`` 为例；其他任务应同时替换生成和回放参数中的任务编号。生成任务卡时使用
``--robot dual_franka --task dual_franka_t0``，回放时使用
``--robot dual_franka --planner flash --task-id 0``，并提供双臂任务卡及配置。
平移标注使用具有深度和有效标定的 ``base``、``d455``、``left_wrist`` 或
``right_wrist`` 相机。移动原语通过 ``arm: left`` 或 ``arm: right`` 指定机械臂；
左臂工作空间检查会把共享的右基座目标坐标转换到左基座坐标系。
