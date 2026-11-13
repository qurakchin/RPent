动作模型参考
============

动作模型接入的协议与部署细节。接入步骤见 :doc:`add_action_model`；本页说明按客户端隔离状态、WAM 通信协议、平台兼容性检查和 worker 部署。

.. page-head::
   :for: 需要动作模型通信协议与部署细节的开发者
   :outcome: 说明按客户端隔离的状态、WAM 协议、平台兼容性和 worker 部署
   :read-when: 调试动作模型服务，或部署 WAM worker 时
   :skip-when: 还没接入模型；先看 :doc:`add_action_model`

**本文结构：** 按客户端隔离策略状态 → 通信与生命周期 → 平台兼容性 → 部署与任务运行。


按客户端隔离策略状态
--------------------

大多数 VLA 后端是无状态的：``predict`` 只做推理，不保存各客户端的中间状态，``session_id`` 可以忽略。但有些模型带按客户端隔离的策略状态，例如 RLDX-1 的 memory/RTC。同一个 ``vla_server`` 服务多个客户端时，各客户端的策略状态会互相污染，必须按 session 隔离。接入分三块：

- **facade 侧**：构造 ``BaseVLAFacade`` 子类时传 ``enable_sessions=True`` 和 ``session_timeout_s``，并实现 ``_on_session_drop``——session 结束（客户端调用 ``session.close`` RPC 或空闲超时）时在这里清理该客户端的策略状态。需要显式重置时，额外提供 ``reset_session`` RPC（只清策略状态，不销毁 session）。``serve`` 必须传 ``session_sweep_s`` （> 0），让后台线程定期回收过期 session。

- **client 侧**：model client 内部的 ``RpcClient`` 以 ``enable_sessions=True`` 构造，连接时自动向 server 注册 session。 ``session_id`` 由 facade 从连接派生并注入 server 端 handler，客户端 **不传**，也不应在 ``predict`` 的 ``options`` 里伪造 ``session_ids``。

- **primitives 侧**：任务开始前调用 ``reset_session`` 清空上一回合残留的策略状态，保证连续多次运行之间状态不串。

通信与生命周期
--------------

RPC 路由为 ``wam.get_model_meta``、``wam.predict`` 和 ``wam.reset``。请求包含 ``images``、``state``、``instruction``、``embodiment`` 和 ``action_space``。模型元数据包含 ``control`` 控制字典、必需相机与状态维度、可执行 ``chunk_size``、后端与 checkpoint 身份及会话设置。预测结果包含 ``actions``，可选返回 ``future_observation``、``value`` 和 ``metadata``。

``BaseWAMClient`` 在构造时查询一次模型元数据并保存在 ``model_meta``，后续预测直接使用该快照。可选的 ``prediction_timeout_s`` 提供客户端请求预算，未提供时默认为 300 秒；显式传入的 client 超时优先。Cosmos3 在原生 HTTP 超时上增加 30 秒作为 RPC 开销余量。

消息直接使用已有传输支持的字典和 NumPy 数组，没有对象到通信格式的转换，也没有协议版本字段。client 和 worker 应从同一份代码部署。连接时，平台将服务的控制字典与本地支持的定义直接比较，并缓存选择；更换服务或控制方式时创建新 client。服务端检查收到的观测，客户端在执行前检查动作形状、chunk 长度及有限数值。decoder 保留夹爪二值化、动作前缀选择等转换之前的必要检查，避免转换隐藏无效输出。

平台 client 用 ``predict()`` 返回动作，用 ``predict_result()`` 返回完整字典。回合复位同时清空环境与模型历史。RoboTwin 复用环境首次初始化的 reset，并在构造 toolkit 时清空模型历史。连接 client 不会复位已有回合；直接使用 client 时，在首次预测前调用 ``reset()``，结束后调用 ``close()``。带会话的 worker 实现 ``reset_native``；当前模型包均只声明一次 ``USES_SESSIONS = False``，供启动逻辑和能力声明共用。

模型依赖安装在单独准备的环境中，RPent 的公共安装不会安装模型 worker 的依赖。自己启动的 worker 复用已有 daemon 生命周期。外部服务在 RPent 停止自己管理的服务后仍保持运行。

添加平台与检查兼容性
--------------------

增加平台时，提供物理观测、原生控制定义、平台 client 及工具和运行时接线。每个模型仍需匹配的 checkpoint 和配对转换；注册本身不能证明权重兼容。RoboTwin 已定义 EEF16 控制方式，但当前 Fast-WAM adapter 使用 qpos14。Cosmos Policy 尚无 RoboTwin adapter。

``future_observation`` 和 ``value`` 为模型预测预留字段，独立的预测与规划 RPC 以及规划器使用预测结果尚未实现。每个 toolkit 必须持有 ``MemoryManager``，并注册记忆文件工具。WAM 默认使用平台记忆根目录下以后端命名的本地子目录，可通过 ``--memory-dir`` 指定目录，语料允许为空。WAM 尚未配置兼容的 HF 经验库，当前评测不支持 HF 记忆、Flash 和探索模式。

.. _action-model-deployment:

动作模型部署与任务运行
----------------------

公共动作模型参数、GPU 选择及兼容别名统一见 :doc:`../guides/cli`。独立 worker 的 ``--help`` 列出其自身不带模型前缀的参数，例如 ``--config`` 和 ``--predict-future``。

独立部署模型服务
~~~~~~~~~~~~~~~~

反复运行任务时，先用下面的命令启动一次 worker，再在每次 RPent 运行时通过 ``--am-endpoint`` 连接。RPent 退出后模型服务继续运行，使用结束后需单独停止。也可以使用后面的单次运行示例，让 RPent 自动启动和停止 worker。

先准备官方模型环境、checkpoint 和辅助文件，并安装 RPent 运行时依赖；``PYTHONPATH`` 只让该环境能导入当前代码，不会安装依赖。仿真器保留在 RPent 环境中。在已准备好的 Cosmos 源码目录启动：

.. code-block:: bash

   PYTHONPATH=/path/to/RPent /path/to/cosmos/.venv/bin/python \
     -m rpent.robots.components.cosmos_policy.server \
     --checkpoint /path/to/cosmos-libero --cuda-device 0 --port 8116

checkpoint 目录包含 ``Cosmos-Policy-LIBERO-Predict2-2B.pt``、``libero_dataset_statistics.json`` 和 ``libero_t5_embeddings.pkl``。可用 ``--dataset-stats``、``--text-embeddings`` 覆盖辅助路径。默认使用 5 步动作去噪、seed 1，每次预测 16 个动作，不生成未来状态和价值。``--cached-instructions-only`` 拒绝未缓存指令，否则由官方运行时处理未缓存文字。``--predict-future`` 可开启可选输出，但 RPent 尚不利用这些输出规划。

在已准备好的 Fast-WAM 环境中启动：

.. code-block:: bash

   CUDA_VISIBLE_DEVICES=0 PYTHONPATH=/path/to/RPent \
     /path/to/fast-wam/venv/bin/python \
     -m rpent.robots.components.fast_wam.server \
     --platform libero --checkpoint /path/to/fast-wam-libero.pt \
     --config /path/to/worker.yaml --dataset-stats /path/to/dataset_stats.json \
     --port 8117

LIBERO worker 的模型环境需要安装 RLinf ``release/v0.4`` 的 Fast-WAM 接入，以及其 ``requirements/install.sh`` 指定的 Fast-WAM 版本（目前为 ``45d8e1458921d83f8ad6cf9ce993d371208dabd0``）。在 RLinf 仓库执行 ``bash requirements/install.sh embodied --model fastwam`` 配套安装；其他 Fast-WAM 版本的 VAE 接口可能不兼容。worker 调用 RLinf 的 ``get_model`` 和 ``predict_action_batch``，图像缩放与拼接、状态归一化、推理及 LIBERO 动作还原均由 RLinf 负责。RPent 只将物理观测映射到 RLinf 输入字段，并从返回动作中移除单环境 batch 维度。RLinf 的该策略尚不支持 RoboTwin 的三相机/qpos14 接口，因此 RoboTwin 保留官方 Fast-WAM 推理路径。

LIBERO 直接使用 RLinf 原生模型 YAML。RPent 从部署参数填入 checkpoint 和统计文件路径。RLinf 再组合官方模型与 processor 配置，并解析推理选项。例如：

.. code-block:: yaml

   action_horizon: 32
   num_action_chunks: 10
   num_inference_steps: 20
   binarize_gripper: true
   seed: 1
   fastwam:
     config_dir: /path/to/FastWAM/configs
     config_name: sim_libero
     overrides: []

官方配置及 overrides 需匹配 checkpoint。模型与 processor 的组合交给 ``fastwam.config_dir/config_name/overrides``，worker 从已加载的 policy 读取可执行 chunk 长度。

RoboTwin 使用 ``--platform robotwin``，并更换为对应 checkpoint 和配置。它的 YAML 提供解析好的 Hydra ``model``、``processor``，后者来自官方配置的 ``data.train.processor``，还需包含 ``action_horizon``、``execute_steps``、``video_size`` 和 ``concat``。``inference_options`` 传给官方 ``model.infer_action``，不能覆盖编码后的观测或 ``action_horizon``。处理未缓存指令时需在模型配置中启用文本编码器。``execute_steps`` 为正数且不超过 ``action_horizon``，是对外声明的可执行 ``chunk_size``。固定三相机布局、合并后的状态/动作字段和禁用 LIBERO 夹爪二值化在启动时检查；预测时仍在截取动作前缀前检查输出形状和有限数值。

Cosmos3 需要转换为 Diffusers 组件格式的任务训练 checkpoint，并按 RLinf 的 ``Cosmos3 SGLang Evaluation`` 指南独立部署 SGLang。使用包含 ``Cosmos3SGLangAdapter`` 的 RLinf 版本及其配套 SGLang 依赖。RPC worker 在该环境中运行：

.. code-block:: bash

   PYTHONPATH=/path/to/RPent:/path/to/RLinf /path/to/sglang-env/bin/python \
     -m rpent.robots.components.cosmos3.server \
     --platform libero --checkpoint nvidia/cosmos3-nano-libero10-sdg-export-S2_s43 \
     --config /path/to/cosmos3.yaml \
     --sglang-endpoint http://127.0.0.1:30000 --port 8118

``--checkpoint`` 标识 SGLang 实际加载的模型；RPC worker 不加载权重，也不要求本机存有权重，但需要配置中引用的本地动作统计文件。``cosmos3.yaml`` 使用解析好的 RLinf 配置，不执行 Hydra ``defaults`` 组合。按标准 Cosmos3 配方训练的 LIBERO rot6d checkpoint 可使用：

.. code-block:: yaml

   env:
     eval:
       env_type: libero
   rollout:
     model:
       raw_action_dim: 10
       action_dim: 7
       action_normalization: quantile_rot
       action_stats_path: /path/to/libero_native_frame_wise_relative_rot6d.json
       num_action_chunks: 16
       action_mode: policy
       action_fps: 20.0
       fps: 20
       num_inference_steps: 30
       action_view_point: ego_view
       num_frames: 17
       size: 320x192
     sglang:
       seed: 1
       http_timeout_s: 600
       server:
         batching_max_size: 1

这些设置和归一化统计必须与 checkpoint 的训练配方匹配。模型进程和 GPU 分配由 SGLang 管理；停止 RPent worker 不会停止 SGLang。RPent 的 ``--am-cuda-device`` 配置本地 RPC worker 进程，不会改变外部服务使用的 GPU。

连接已有服务运行任务
~~~~~~~~~~~~~~~~~~~~

准备好平台资产和 planner 凭据后，在 RPent 仿真器环境中运行下面任一示例（前置配置见 :doc:`../simulators/libero`）：

.. code-block:: bash

   # Cosmos worker already running on port 8116.
   rpent --robot libero --suite libero_spatial --task 0 \
     --am-backend cosmos-policy --am-endpoint http://127.0.0.1:8116 \
     --memory-profile local --planner api --model openai:gpt-5.5

   # Fast-WAM worker already running on port 8117.
   rpent --robot libero --suite libero_spatial --task 0 \
     --am-backend fast-wam --am-endpoint http://127.0.0.1:8117 \
     --memory-profile local --planner api --model openai:gpt-5.5

   # Cosmos3 RPC worker already running on port 8118.
   rpent --robot libero --suite libero_10 --task 0 \
     --am-backend cosmos3 --am-endpoint http://127.0.0.1:8118 \
     --memory-profile local --planner api --model openai:gpt-5.5

之后修改 task 或 suite 即可继续使用兼容的 worker。模型路径和推理选项在部署服务时配置，无需在每次任务命令中重复填写。planner 模型可换成你已配置的供应商支持的模型。RoboTwin 的任务命令见 :doc:`../simulators/robotwin`。

由 RPent 在每次运行时启动服务
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

下面的示例会在每次运行时启动新的 worker，并在退出时停止它。模型环境和文件与独立部署相同；RPent 不会自动下载权重或安装模型依赖。将示例路径替换为实际部署路径：

.. code-block:: bash

   rpent --robot libero --suite libero_spatial --task 0 \
     --am-backend pi05 --am-checkpoint /path/to/pi05-libero \
     --am-python /path/to/pi05-env/bin/python \
     --planner api --model openai:gpt-5.5

   rpent --robot libero --suite libero_spatial --task 0 \
     --am-backend cosmos-policy --am-checkpoint /path/to/cosmos-libero \
     --am-python /path/to/cosmos/.venv/bin/python --am-root /path/to/cosmos \
     --memory-profile local --planner api --model openai:gpt-5.5

   rpent --robot libero --suite libero_spatial --task 0 \
     --am-backend fast-wam --am-checkpoint /path/to/fast-wam-libero.pt \
     --am-python /path/to/fast-wam/venv/bin/python \
     --fast-wam-config /path/to/worker.yaml \
     --fast-wam-dataset-stats /path/to/dataset_stats.json \
     --memory-profile local --planner api --model openai:gpt-5.5

``--am-endpoint`` 与 ``--am-checkpoint`` 互斥。Cosmos 需要 ``--am-root``，也可用 ``COSMOS_POLICY_PYTHON`` 和 ``COSMOS_POLICY_ROOT`` 分别提供 Python 路径和工作目录的默认值。Fast-WAM 必须同时提供 ``--fast-wam-config`` 和 ``--fast-wam-dataset-stats``。

Cosmos3 需要 ``--cosmos3-config`` 和 ``--cosmos3-sglang-endpoint``；该方式只启动 RPC worker，连接已经运行的 SGLang 服务。
