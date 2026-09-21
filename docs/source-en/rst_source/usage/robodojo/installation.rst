RoboDojo Backend Installation & Reproduction
=============================================

This page summarizes the RoboDojo backend setup. The authoritative,
command-complete guide (three-runtime layout, editable IsaacLab, CuRobo, the
JAX-to-PyTorch checkpoint conversion, norm stats, and every required
environment variable) is ``docs/ROBODOJO_INSTALLATION.md``.

The summary below was validated end-to-end on a Linux x86_64 workstation
(NVIDIA RTX PRO 6000 Blackwell, driver 580.173.02, Ubuntu 24.04); the
observations in the authoritative guide were reproduced separately on an RTX
4090 (driver 550.127.08).

Runtime composition
-------------------

The integration keeps three isolated runtimes, plus large assets and one
planner credential; RPent only orchestrates them and never mixes them:

.. list-table::
   :header-rows: 1

   * - Runtime
     - Python
     - Contents
     - Purpose
   * - RPent venv
     - 3.11
     - rpent itself + SAM3
     - agent loop / tools / memory
   * - robodojo-sim
     - 3.11
     - Isaac Sim 5.1 / IsaacLab 0.54.3 / CuRobo (or import stub)
     - simulation
   * - Pi0.5 policy env (uv)
     - 3.11
     - RLinf + rpent-openpi (openpi Pi0.5)
     - policy server

Prerequisites
-------------

* Linux x86_64, NVIDIA GPU, ~100-180 GB disk;
* RoboDojo official checkpoint (``RoboDojo-sim-arx_x5-joint-0``, published
  ~44.7 GB, not fully downloaded in this reproduction) and the ``Assets/``
  tree (measured 15,365 files / 41.27 GB, 39 GiB) from ModelScope;
* SAM3 checkpoint (~3.45 GB) plus the CLIP BPE vocabulary (bundled in the
  sam3 wheel);
* driver: upstream requires 570.x or newer (CUDA 12.8); driver 550 was
  observed to work via CUDA 12.x minor-version compatibility.

RPent + SAM3
------------

.. code-block:: bash

   # Install from the PARENT of the rpent checkout so the sim-only
   # [tool.uv] override-dependencies are not applied to the agent stack.
   uv pip install -e "./rpent[robodojo]"   # full RoboDojo install

``.[robodojo]`` is the only correct RoboDojo extra: it pulls ``robodojo-sim``
plus ``sam3`` plus the pinned ``rlinf`` / ``rpent-openpi`` git dependencies.
There is no ``openpi`` extra, and ``.[sam3]`` alone is missing Isaac Sim /
IsaacLab / CuRobo. On Blackwell, pin ``torch==2.7.1+cu128`` /
``torchvision==0.22.1+cu128``.

RoboDojo sources
----------------

Clone the official RoboDojo repository (including the XPolicyLab submodule) and
pin it to the validated commit. The RPent runner reads the workspace file
``<ROBODOJO_WORKSPACE>/config/runtime.env``; its keys are
``ROBODOJO_SOURCE_ROOT``, ``ROBODOJO_XPOLICYLAB_ROOT``, ``ROBODOJO_SIM_ENV``,
and ``ROBODOJO_PI05_ENV``.

Simulation environment (Isaac Sim / IsaacLab / CuRobo)
------------------------------------------------------

* ``isaacsim[all,extscache]==5.1.0``;
* the pinned IsaacLab 0.54.3 fork. IsaacLab MUST be installed EDITABLE
  (``-e source/isaaclab`` plus ``_assets`` and ``_tasks``): a non-editable
  VCS-subdirectory install ships only ``__init__.py`` and loses
  ``config/extension.toml``. The ``robodojo-sim`` extra's git references exist
  only to keep the extra resolvable, not as a working IsaacLab install;
* ``h5py`` must be added to the sim env (``isaaclab_tasks`` imports it);
* CuRobo is imported at module level by
  ``env/robot_manager/robot_manager.py`` ->
  ``env/planner_manager/curobo_planner``. The pinned fork is a v2 rewrite that
  JIT-compiles kernels at runtime via ``cuda.core``, so ``nvidia-curobo[cu12]``
  installs as a normal Python package (no CUDA build at install time); kernels
  compile on the first planner construction. Install it editable for working
  IK / ee actions, or use an import-only stub plus conditional
  ``need_planner: False`` on machines without it. The stub must NOT be on
  ``PYTHONPATH`` when real CuRobo is installed: ``PYTHONPATH`` precedes
  ``site-packages``, so it would shadow the real package;
* REQUIRED after cloning the assets: generate the real planner config by
  running ``python utils/update_embodiment_config_path.py`` from the RoboDojo
  repo root. It writes ``Assets/Robots/<robot>/curobo.yml`` and bakes ABSOLUTE
  asset paths, so re-run it whenever the repo or asset location changes.
  Without it ``CuroboPlanner`` dies with
  ``FileNotFoundError: .../Assets/Robots/x5/curobo.yml``. With it, the env
  server logs ``CuRobo planner AVAILABLE`` and ``env.get_status`` reports
  ``ik_available: true``.

RoboDojo assets
---------------

The measured ``Assets/`` tree is 15,365 files / 41.27 GB (39 GiB). The
``14,506`` LFS-file and ``9,224`` eval-layout counts previously quoted here
could not be verified against the pinned checkout; treat them as unverified.

Pi0.5 policy environment
------------------------

Build a separate env with RLinf plus ``rpent-openpi`` (openpi Pi0.5), then
convert the published JAX/orbax checkpoint to PyTorch, because the loader only
accepts ``*.safetensors`` or ``model_state_dict/full_weights.pt``:

.. code-block:: bash

   ln -sfn <ckpt>/59999 ckpt_torch/jax_pi05_src
   venv_policy/bin/python -m rlinf.utils.ckpt_convertor.convert_openpi_jax_to_python \
     --checkpoint-dir "$PWD/ckpt_torch/jax_pi05_src" \
     --output-path  "$PWD/ckpt_torch/pi05_robodojo_arx_x5" \
     --config-name pi05_aloha --precision bfloat16

Run it as a module (a script-path invocation makes
``rlinf/utils/ckpt_convertor/openpi/`` shadow the real ``openpi`` package), and
make sure ``--checkpoint-dir`` contains the lowercase token ``pi05`` (the
converter branches on that substring).

Wiring & smoke test
-------------------

``robots/robodojo/robot_spec.py`` reads
``<ROBODOJO_WORKSPACE>/config/runtime.env`` (``ROBODOJO_SIM_ENV``,
``ROBODOJO_PI05_ENV``, ``ROBODOJO_SOURCE_ROOT``, ``ROBODOJO_XPOLICYLAB_ROOT``);
set ``ROBODOJO_WORKSPACE`` so the CLI finds it. Required env vars:
``PI05_CHECKPOINT_PATH``, ``PI05_NORM_STATS_PATH`` (the DIRECTORY containing
``norm_stats.json``), ``SAM3_CHECKPOINT_PATH``, and the LLM credential
(``claude_code`` checks ``ANTHROPIC_API_KEY`` exactly). Smoke chain:

.. code-block:: text

   robodojo.sh doctor (RoboDojo workspace) -> official Pi0.5 debug gate ->
   bare eval -> rpent --robot robodojo ...

Observed peak VRAM for the full three-service run was 20,242 MiB on a 24 GB
card (env ~6.6 GB, Pi0.5 ~7.9 GB, SAM3 ~4 GB). The earlier ``~45 GB`` figure
described a different host and should not be used for planning. Full command
sequences, troubleshooting, and known pins are in
``docs/ROBODOJO_INSTALLATION.md`` and ``robots/robodojo/guides/interface.md``.
