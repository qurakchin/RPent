RoboDojo 参考
=============

RoboDojo 的模型 worker 配置与离线资源。安装和任务运行见 :doc:`robodojo`。

.. page-head::
   :for: 要为 RoboDojo 准备 VPP2 或 Awomo05 策略素材的开发者
   :outcome: 准备策略客户端、checkpoint，以及可选的本地 NVIDIA 场景素材
   :read-when: RoboDojo 页面把你引到 VPP2、Awomo05 或离线素材配置时
   :skip-when: 还没有安装 RoboDojo；先看 :doc:`robodojo`

**Page map:** VPP2 配置 → Awomo05 配置 → 可选离线资源。


VPP2 配置
---------

准备上面的 VPP2 实现和配对权重。资源目录可以自行选择；以下以 ``/path/to/vpp2`` 为例，使用时替换为自己的目录：

.. code-block:: bash

   export VPP2_MODEL_PATH=/path/to/vpp2
   git clone --no-checkout https://github.com/roboterax/video-prediction-policy-2.git \
     "$VPP2_MODEL_PATH/policy"
   git -C "$VPP2_MODEL_PATH/policy" checkout 72c17acf022494ff63617be86079bb92e92f5bf8
   hf download Haodong082399/VPP2 --local-dir "$VPP2_MODEL_PATH" \
     --include 'checkpoints/joint2b_s100000/**' \
     --include 'checkpoints/Wan2.1-I2V-14B-480P/**'

资源根目录采用以下布局，子目录可以通过软链接复用已有资源：

.. code-block:: text

   vpp2/
   ├── policy/src/vpp2/policy.py
   └── checkpoints/
       ├── joint2b_s100000/
       │   ├── action.pt
       │   ├── video.pt
       │   └── dataset_stats.json
       └── Wan2.1-I2V-14B-480P/

按固定版本的 `推理环境说明 <https://github.com/roboterax/video-prediction-policy-2/blob/72c17acf022494ff63617be86079bb92e92f5bf8/docs/robodojo.md#policy-environment>`_ 安装模型依赖。这些依赖与 ``.[robodojo-sim]`` 分开安装。模型依赖与 RPent 环境兼容时，设置 ``VPP2_MODEL_PATH`` 即可自动启动本地服务，``--am-checkpoint`` 可覆盖该路径。本地服务默认使用 RPent 当前的 Python 解释器；使用 ``--am-python`` 可指定独立模型环境。模型在单张 GPU 上完整加载。

若使用独立模型环境，在该环境中安装策略依赖和 RPent 核心包，然后启动服务：

.. code-block:: bash

   python -m robots.robodojo.vpp2_server --model-path /path/to/vpp2 \
     --host 127.0.0.1 --port 9201

在 RPent／仿真环境的任务命令中添加 ``--am-endpoint socket://127.0.0.1:9201``。RPent 负责启动和关闭自己创建的模型进程；独立启动的服务由其启动者管理。远端部署见 :doc:`../guides/advanced_deployment`。

Awomo05 配置
------------

准备上面的 Awomo05 评测实现和配对权重。资源目录可以自行选择；以下以 ``/path/to/awomo05`` 为例，使用时替换为自己的目录：

.. code-block:: bash

   export AWOMO05_MODEL_PATH=/path/to/awomo05
   git clone --no-checkout https://github.com/RoboDojo-Benchmark/RoboDojo.git \
     "$AWOMO05_MODEL_PATH/policy"
   git -C "$AWOMO05_MODEL_PATH/policy" checkout 2184bf8844ea9d205382c4aefa3a694311418251
   git -C "$AWOMO05_MODEL_PATH/policy" submodule update --init XPolicyLab
   git -C "$AWOMO05_MODEL_PATH/policy/XPolicyLab" fetch origin 562c14cf08b9e6e411e7d76f192740afced77160
   git -C "$AWOMO05_MODEL_PATH/policy/XPolicyLab" checkout 562c14cf08b9e6e411e7d76f192740afced77160
   export AWOMO05_WEIGHTS="$AWOMO05_MODEL_PATH/checkpoints"
   bash "$AWOMO05_MODEL_PATH/policy/XPolicyLab/policy/Awomo05/download_weights.sh"

资源根目录采用以下布局，子目录可以通过软链接复用已有资源：

.. code-block:: text

   awomo05/
   ├── policy/
   │   ├── env_cfg/arx_x5.yml
   │   └── XPolicyLab/policy/Awomo05/model.py
   └── checkpoints/
       ├── model.pt
       ├── dataset_stats.json
       ├── flux2-klein-base-4b/
       ├── flux2-dev/
       └── Qwen3-VL-4B-Instruct/

按固定版本的 `推理环境说明 <https://github.com/XPolicyLab/XPolicyLab/blob/562c14cf08b9e6e411e7d76f192740afced77160/policy/Awomo05/README.md>`__ 安装模型依赖。这些依赖与 ``.[robodojo-sim]`` 分开安装。模型依赖与 RPent 环境兼容时，设置 ``AWOMO05_MODEL_PATH`` 即可自动启动本地服务，``--am-checkpoint`` 可覆盖该路径。本地服务默认使用 RPent 当前的 Python 解释器；使用 ``--am-python`` 可指定独立模型环境。模型在单张 GPU 上完整加载。

若使用独立模型环境，在该环境中安装策略依赖和 RPent 核心包，然后启动服务：

.. code-block:: bash

   python -m robots.robodojo.awomo05_server --model-path /path/to/awomo05 \
     --host 127.0.0.1 --port 9205

在 RPent／仿真环境的任务命令中添加 ``--am-endpoint socket://127.0.0.1:9205``。RPent 负责启动和关闭自己创建的模型进程；独立启动的服务由其启动者管理。远端部署见 :doc:`../guides/advanced_deployment`。

.. _robodojo-local-nvidia-assets:

NVIDIA 场景素材的本地准备（可选）
---------------------------------

以下两类用户需要预先下载 NVIDIA 场景素材：

- 需要在无法联网的机器上运行仿真的用户。
- 运行时无法稳定访问 NVIDIA 资源地址，日志中相关文件反复下载失败的用户。

RoboDojo 场景还会引用 NVIDIA 提供的三维模型、材质和贴图。这些文件与前面下载的 RoboDojo 资源分开提供，默认在加载场景时通过网络获取。\
场景能正常加载时，可跳过本节，无需下载本地资产包，也不用设置 ``ROBODOJO_USD_ASSET_PREFIX``。

以下步骤用于准备 ``Assets/Isaac/5.0`` 路径对应的本地资源。完整资产包的三个分卷合计约 150 GB，并非单个 RoboDojo 场景所需的下载量；\
合并和解压还需额外空间。离线机器可先在能联网的机器上下载，再将分卷复制到 ``/path/to/nvidia-assets``。

.. code-block:: bash

   mkdir -p /path/to/nvidia-assets

   # 下载三个分卷，已有下载可断点续传
   wget -c -P /path/to/nvidia-assets \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.001 \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.002 \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.003

   # 合并并解压，保留 Assets/Isaac/5.0 目录结构
   cat /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.001 \
       /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.002 \
       /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.003 \
     > /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip
   unzip /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip -d /path/to/nvidia-assets

   test -d /path/to/nvidia-assets/Assets/Isaac/5.0/Isaac
   test -d /path/to/nvidia-assets/Assets/Isaac/5.0/NVIDIA

在运行 RPent 的终端中设置以下变量，再运行任务：

.. code-block:: bash

   export ROBODOJO_USD_ASSET_PREFIX=/path/to/nvidia-assets

这会将 RoboDojo 匹配的 5.0 在线资源地址改为本地路径。它并不代表所有 Isaac Sim 资源均可离线使用；\
若仍有其他在线资源加载失败（例如 ``Assets/Isaac/5.1`` 路径），需另外准备对应版本的资产并配置本地加载，\
见 `NVIDIA 本地资产说明 <https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_faq.html#isaac-sim-setup-assets-content-pack>`_。
