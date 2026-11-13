RoboDojo Reference
==================

Model worker setup and offline assets for RoboDojo. Installation and the task loop are in :doc:`robodojo`.

.. page-head::
   :for: Developers preparing VPP2 or Awomo05 policy assets for RoboDojo
   :outcome: You can prepare the policy client, checkpoint, and optional local NVIDIA scene assets
   :read-when: The RoboDojo page points here for VPP2, Awomo05, or offline asset setup
   :skip-when: You have not installed RoboDojo; start with :doc:`robodojo`

**Page map:** VPP2 setup → Awomo05 setup → optional offline assets.


VPP2 Setup
----------

Prepare the VPP2 implementation and paired weights above. Choose a resource
directory and replace ``/path/to/vpp2`` with your own directory:

.. code-block:: bash

   export VPP2_MODEL_PATH=/path/to/vpp2
   git clone --no-checkout https://github.com/roboterax/video-prediction-policy-2.git \
     "$VPP2_MODEL_PATH/policy"
   git -C "$VPP2_MODEL_PATH/policy" checkout 72c17acf022494ff63617be86079bb92e92f5bf8
   hf download Haodong082399/VPP2 --local-dir "$VPP2_MODEL_PATH" \
     --include 'checkpoints/joint2b_s100000/**' \
     --include 'checkpoints/Wan2.1-I2V-14B-480P/**'

The resource root has the following layout. Subdirectories may be symbolic
links to existing resources:

.. code-block:: text

   vpp2/
   ├── policy/src/vpp2/policy.py
   └── checkpoints/
       ├── joint2b_s100000/
       │   ├── action.pt
       │   ├── video.pt
       │   └── dataset_stats.json
       └── Wan2.1-I2V-14B-480P/

Install the model dependencies using the pinned project's
`inference environment instructions
<https://github.com/roboterax/video-prediction-policy-2/blob/72c17acf022494ff63617be86079bb92e92f5bf8/docs/robodojo.md#policy-environment>`_.
These dependencies are separate from ``.[robodojo-sim]``. When they are
compatible with the RPent environment, ``VPP2_MODEL_PATH`` enables automatic
local startup; ``--am-checkpoint`` overrides it. The local server loads the
full model on one GPU. It defaults to RPent's Python interpreter; use
``--am-python`` to select a separate model environment.

To use a separate model environment, install the policy dependencies and RPent's
core package there, then start the service:

.. code-block:: bash

   python -m robots.robodojo.vpp2_server --model-path /path/to/vpp2 \
     --host 127.0.0.1 --port 9201

Add ``--am-endpoint socket://127.0.0.1:9201`` to the task command in the
RPent/simulator environment. RPent starts and stops its own model process;
independently started services remain under their operator's control.
For remote deployment, see :doc:`../guides/advanced_deployment`.

Awomo05 Setup
-------------

Prepare the Awomo05 evaluation implementation and paired weights above.
Choose a resource directory and replace ``/path/to/awomo05`` with your own directory:

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

The resource root has the following layout. Subdirectories may be symbolic
links to existing resources:

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

Install the model dependencies using the pinned project's
`inference environment instructions <https://github.com/XPolicyLab/XPolicyLab/blob/562c14cf08b9e6e411e7d76f192740afced77160/policy/Awomo05/README.md>`__.
These dependencies are separate from ``.[robodojo-sim]``. When the model
dependencies are compatible with the RPent environment,
``AWOMO05_MODEL_PATH`` enables automatic local startup; ``--am-checkpoint``
overrides it. The local server loads the full model on one GPU. It defaults
to RPent's Python interpreter; use ``--am-python`` to select a separate model
environment.

To use a separate model environment, install the policy dependencies and RPent's
core package there, then start the service:

.. code-block:: bash

   python -m robots.robodojo.awomo05_server --model-path /path/to/awomo05 \
     --host 127.0.0.1 --port 9205

Add ``--am-endpoint socket://127.0.0.1:9205`` to the task command in the
RPent/simulator environment. RPent starts and stops its own model process;
independently started services remain under their operator's control.
For remote deployment, see :doc:`../guides/advanced_deployment`.

.. _robodojo-local-nvidia-assets:

Prepare Local NVIDIA Scene Assets (Optional)
--------------------------------------------

Download NVIDIA scene assets in advance if either of these applies:

- You need to run the simulator on a machine without network access.
- NVIDIA resource URLs are unreliable and the logs show repeated download failures.

RoboDojo scenes also reference NVIDIA 3D models, materials, and textures.
These files are separate from the RoboDojo resources downloaded above and
load over the network by default. Skip this section if scenes load normally;
you do not need a local asset pack or ``ROBODOJO_USD_ASSET_PREFIX``.

The steps below prepare local resources for ``Assets/Isaac/5.0`` paths.
The three parts of the complete asset pack total about 150 GB; this is not
the download size for a single RoboDojo scene. Allow extra space for merging
and extraction. For an offline machine, download the parts on a connected
machine first, then copy them to ``/path/to/nvidia-assets``.

.. code-block:: bash

   mkdir -p /path/to/nvidia-assets

   # Download all three parts; interrupted downloads can resume
   wget -c -P /path/to/nvidia-assets \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.001 \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.002 \
     https://download.isaacsim.omniverse.nvidia.com/isaac-sim-assets-complete-5.0.0.zip.003

   # Merge and extract, preserving the Assets/Isaac/5.0 directory structure
   cat /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.001 \
       /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.002 \
       /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip.003 \
     > /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip
   unzip /path/to/nvidia-assets/isaac-sim-assets-complete-5.0.0.zip -d /path/to/nvidia-assets

   test -d /path/to/nvidia-assets/Assets/Isaac/5.0/Isaac
   test -d /path/to/nvidia-assets/Assets/Isaac/5.0/NVIDIA

Set this variable in the terminal that will run RPent, then run the task:

.. code-block:: bash

   export ROBODOJO_USD_ASSET_PREFIX=/path/to/nvidia-assets

This changes the matching RoboDojo 5.0 resource URLs to local paths. It does
not make every Isaac Sim resource available offline. If other online resources
still fail to load, such as ``Assets/Isaac/5.1`` paths, prepare assets for that
version and configure local loading separately. See the
`NVIDIA local asset instructions
<https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_faq.html#isaac-sim-setup-assets-content-pack>`_.
