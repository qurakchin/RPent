Quick Start
===========

Install RPent, run one LIBERO-PRO task, and inspect its result. This example uses the Claude Code planner, Pi0.5 for robot actions, and SAM3 for visual segmentation.

For another platform, follow :doc:`../simulators/robocasa`, :doc:`../simulators/robotwin`, or :doc:`real-world robot deployment <../real_world_robots/index>` and use that platform’s requirements.

**Page map:** requirements and resource estimates → install → download assets and models → configure the planner → run one task → inspect the result → recover from a failed step.

Requirements
------------

- Linux, an NVIDIA GPU, and a driver compatible with the selected PyTorch CUDA build.
- ``git``, ``bash``, and a C/C++ toolchain.
- `uv <https://docs.astral.sh/uv/getting-started/installation/>`_ to create an isolated Python environment. These commands use Python 3.11.
- Credentials for the Claude Code planner: either an ``ANTHROPIC_API_KEY`` with access to the example model, or a Claude Code login created with ``claude auth login``. You also need network access to download assets and weights; model calls incur API charges.

Resource estimates
~~~~~~~~~~~~~~~~~~

These estimates cover this LIBERO-PRO setup; they are not a hardware certification.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Resource
     - Estimate
   * - GPU memory
     - Allow at least 16 GB to run Pi0.5 and SAM3 on one GPU. Pi0.5 inference needs more than 8 GB, and SAM3 loads a 3.4 GB checkpoint; split the services with ``--am-cuda-device`` and ``--sam3-cuda-device`` when memory is tight.
   * - Disk
     - About 60 GB free: LIBERO datasets (~34 GB), scene assets (~0.6 GB), model weights (~11 GB), and the Python environment.
   * - Model downloads
     - Pi0.5 ``model.safetensors`` is 7.5 GB; the command below skips the 13.5 GB ``optimizer.pt``. ``sam3.pt`` is 3.4 GB.
   * - Run time
     - Typically 5–15 minutes per episode with an online planner; planner, model, and reasoning effort dominate. Reported means are on :doc:`Time & Token Costs <../leaderboard/time-token-costs>`.

.. _quickstart-install:

1. Install RPent
----------------

The steps in this section are the reference installation. Platform pages add
only their extra package, Python version, or system dependencies.

Create and activate an isolated Python environment:

.. code-block:: bash

   git clone https://github.com/RLinf/RPent.git
   cd RPent
   uv venv --python 3.11
   source .venv/bin/activate

Install the PyTorch build required by OpenPI. This command uses the CUDA 12.8
index; replace ``cu128`` with the index for your GPU and NVIDIA driver from the
`PyTorch previous-versions page <https://pytorch.org/get-started/previous-versions/>`_.
Then install LIBERO-PRO:

.. code-block:: bash

   uv pip install "torch==2.7.1" "torchvision==0.22.1" \
     --index-url https://download.pytorch.org/whl/cu128
   uv pip install -e ".[libero-pro]"

Run the remaining commands in this terminal from the RPent repository root. In a new terminal, activate ``.venv`` and set the checkpoint paths again, and export the API key if you use one.

2. Download Assets and Models
-----------------------------

Download the LIBERO-PRO scene assets. ``--skip-existing`` reuses files already downloaded:

.. code-block:: bash

   liberopro-download-assets --skip-existing

Download Pi0.5 and SAM3, then set their paths:

.. code-block:: bash

   uv pip install "huggingface_hub>=0.34,<1.0" modelscope
   hf download RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT \
     --exclude optimizer.pt \
     --local-dir ./checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT
   modelscope download --model facebook/sam3 sam3.pt \
     --local_dir ./checkpoints/sam3

   export PI05_CHECKPOINT_PATH="$PWD/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT"
   export SAM3_CHECKPOINT_PATH="$PWD/checkpoints/sam3/sam3.pt"

Pi0.5 executes robot actions; SAM3 locates objects in images. SAM3 is also available on Hugging Face; see :doc:`../simulators/libero` for access and alternative download instructions.

3. Configure and Check the Planner
----------------------------------

Export an API key if you use one. A ``claude auth login`` session is also accepted, in which case skip the ``export`` line. Then check the planner:

.. code-block:: bash

   export ANTHROPIC_API_KEY="YOUR_API_KEY"
   rpent-check-llm --planner claude_code --model claude-opus-4-8

The official Anthropic endpoint needs no ``ANTHROPIC_BASE_URL`` setting. See :doc:`../guides/configure_planner` for custom endpoints and other planners. Proceed after the check passes; it verifies model-service authentication and connectivity. The check reports a missing key only when it detects neither an API key nor a Claude Code login.

4. Run Your First Task
----------------------

Run task ``2`` in ``libero_object_swap`` with scene seed ``0``:

.. code-block:: bash

   rpent --robot libero --libero-type pro \
     --suite libero_object_swap --task 2 --seed 0 \
     --planner claude_code --model claude-opus-4-8 \
     --output-dir ./logs/first-libero-pro

The terminal shows environment, VLA, and SAM3 service startup, followed by planner messages and tool calls. Inspect ``logs/first-libero-pro/`` when the run ends. Choose a new output directory for later runs to preserve this record.

5. Inspect the Result
---------------------

- ``episode.mp4``: replay the robot’s actions.
- ``transcript_*.json``: inspect planner messages, tool calls, and the finish state.
- ``run.log``: inspect runtime messages and errors.

For LIBERO, success is the top-level ``terminated`` value in the final environment state, available in the result of ``view_env_state(step=-1)``. The planner’s ``finish`` status alone does not establish environment success.

See :ref:`run-output-files` for default directory names, exported action sequences, and step artifacts.

See :ref:`dashboard-usage` to watch cameras and actions live. For more tasks, exploration, and experiment reproduction, continue with :doc:`../simulators/libero`.

.. _quickstart-interactive:

For terminal interaction, add ``--tui`` (``-t``) to enter follow-up
instructions. It cannot be combined with ``--dashboard``. See
:ref:`terminal-interaction` for planner-specific controls.

Common Problems
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Symptom
     - Action
   * - Model connection fails
     - Check the key, model access, and endpoint; rerun ``rpent-check-llm``.
   * - Asset download fails
     - Rerun the download. ``--skip-existing`` is an option of the LIBERO-PRO package's ``liberopro-download-assets`` helper, not of ``rpent``. If Hugging Face is slow, optionally set ``HF_ENDPOINT=https://hf-mirror.com`` for that command.
   * - Model download fails on Hugging Face
     - For gated weights, request access on the model page and run ``hf auth login``; then retry. If the service is slow, set ``HF_ENDPOINT`` as above, or use the ModelScope command on this page for SAM3.
   * - Model download fails on ModelScope
     - Rerun the command. If ModelScope keeps failing, use the Hugging Face alternative in :doc:`../simulators/libero` and point ``SAM3_CHECKPOINT_PATH`` at the downloaded file.
   * - Environment or model fails to start
     - Check both checkpoint paths, then inspect ``env_server.log``, ``vla_server.log``, or ``sam3_server.log``. For out-of-memory errors, check other GPU processes.
   * - Task runs but does not succeed
     - Review the video and final state to distinguish action failures from service errors. One task does not establish benchmark performance.
