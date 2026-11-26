Testing and CI
==============

GitHub runs the CPU unit tests and reports line coverage in the test logs.
On same-repository PRs and pushes to ``main``, **Simulator CI** selects
environment builds and GPU suites from the changed paths. For example,
RLDX changes select RoboCasa. Shared planner changes select all seven suites.
Documentation-only changes select none. The workflow log also lists selected targets for fork PRs.

Each selected GPU job starts Qwen3.5-2B on the runner CPU and uses the GPU for
the robot stack. RPent asks the model to call each advertised tool one at a time,
then call ``finish``. The job uploads ``tool-coverage.json`` alongside the JUnit
and server logs. Check the missing tools and failed calls there.

The first run installs the pinned llama.cpp binary, weights and vision projector.
To preload them on a Linux x86-64 runner host, run this command from the repository root.

.. code-block:: bash

   bash tests/e2e_tests/provision_planner.sh /mnt/public/rpent_shared/models/ci-qwen35-2b

Test Structure
--------------

``tests/`` contains three top-level directories:

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Directory
     - Scope
   * - ``tests/unit_tests/``
     - Offline CPU unit tests that run without a GPU, simulator, or model weights. They verify interfaces, configuration parsing, data transforms, and process cleanup using lightweight in-memory test doubles.
   * - ``tests/tooling/``
     - Standalone scripts that validate repository layout, ``component.toml`` manifests, and import boundaries before any Python environment is installed.
   * - ``tests/e2e_tests/``
     - GPU end-to-end tests that start real simulators and model servers, together with shared helpers (``common.py``) and the clean-environment runner (``run_gpu_suite.sh``).

Unit test directories mirror the source tree:

.. list-table::
   :header-rows: 1
   :widths: 36 64

   * - Source directory
     - Unit test directory
   * - ``rpent/<module>``
     - ``tests/unit_tests/rpent/<module>/``
   * - ``robots/<name>/``
     - ``tests/unit_tests/robots/<name>/``
   * - ``components/models/<name>/``
     - ``tests/unit_tests/components/models/``
   * - ``components/tools/<name>/``
     - ``tests/unit_tests/components/tools/``
   * - ``component.toml`` install manifests
     - Validated by ``tests/unit_tests/installs/`` and ``./tests/tooling/run.sh layout``

Follow these conventions when adding tests:

- Keep test helper classes and setup code inside the test file that uses them; move shared setup helpers to ``conftest.py`` only when multiple test files reuse them.
- Name test files after their focus: ``*_contracts.py`` for public APIs and configuration, ``*_loopback.py`` for local socket or HTTP communication, ``*_lifecycle.py`` for startup and cleanup, and ``*_smoke.py`` for basic startup checks.
- Keep ``tests/unit_tests/rpent/install/`` focused on installer logic using temporary directories, and keep checks on the checked-in ``component.toml`` files in ``tests/unit_tests/installs/``.

Tests Required for a New Robot or Model
---------------------------------------

Adding a Robot or Simulator
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When adding a robot under ``robots/<name>/`` (and an optional simulator under ``components/sim/<name>/``):

1. **Offline CPU unit tests** under ``tests/unit_tests/robots/<name>/``:

   - Verify robot registration, CLI flags, configuration parsing, prompts, and tool schemas.
   - Verify CLI execution, local RPC communication, and child-process cleanup using lightweight local test servers instead of real simulators or models.
   - Run ``./tests/tooling/run.sh layout`` and ``tests/unit_tests/installs/`` to verify ``component.toml`` and import boundaries.

2. **GPU end-to-end tests** under ``tests/e2e_tests/<name>/`` (reusing helpers in ``tests/e2e_tests/common.py``):

   - **Environment smoke** (``test_environment_smoke.py`` or an environment case in ``test_components.py``): start the simulator with assets and GPU/EGL only (no model weights), reset it, execute a basic action, read observations, and close cleanly.
   - **Model component** (``test_components.py``): send a real simulator observation to the model server, obtain a predicted action, and execute it.
   - **Planner tool coverage** (``test_policy_chain.py``): call ``run_policy_chain`` with the local Qwen model to exercise the public CLI, verify saved outputs, and confirm all background processes exit.

3. **CI registration**:

   - Add a target to ``tests/e2e_tests/run_gpu_suite.sh`` and map its install component to the suite in ``tests/tooling/ci_targets.py``.

See :doc:`add_robot` for the full robot integration guide.

Adding a Model
~~~~~~~~~~~~~~

When adding an action model or perception model under ``components/models/<name>/``:

1. **Offline CPU unit tests** under ``tests/unit_tests/components/models/`` (and ``tests/unit_tests/robots/<robot>/`` for robot-specific adapters):

   - Verify configuration validation, startup arguments, and observation/action format conversion.
   - Verify local HTTP/socket communication with a lightweight test backend, including session isolation, reset, error handling, and worker shutdown.

2. **GPU end-to-end cases** in each supported robot's ``tests/e2e_tests/<robot>/``:

   - Add a model inference case in ``test_components.py`` and a planner tool coverage case in ``test_policy_chain.py``.
   - Guard model cases with ``require_model_path`` (or the model's interpreter/endpoint check) so missing checkpoints skip only the dependent cases rather than failing the simulator suite.

3. **CI registration**:

   - Add the model's checkpoint, interpreter, or endpoint environment variables to the **Embodied GPU E2E** workflow (leave unavailable paths empty so CI skips only dependent cases).

See :doc:`add_action_model` for the full action-model integration guide.

Run Tests Locally
-----------------

Run Offline Tests Locally
~~~~~~~~~~~~~~~~~~~~~~~~~

Install ``infra-unit_cpu`` (which includes CPU PyTorch required by model-server unit tests) and run pytest:

.. code-block:: bash

   ./rpent-install.sh install infra-unit_cpu --venv .venv-unit-cpu
   .venv-unit-cpu/bin/python -m pytest tests/unit_tests -v
   .venv-unit-cpu/bin/python -m pytest tests/unit_tests/robots/<name> -v

Run the repository layout check without activating a virtualenv:

.. code-block:: bash

   ./tests/tooling/run.sh layout

Run GPU Suites Locally
~~~~~~~~~~~~~~~~~~~~~~

On a host with a dedicated NVIDIA GPU, EGL, and the target's assets and checkpoints, pass two new directories for test outputs and virtualenvs:

.. code-block:: bash

   export CUDA_VISIBLE_DEVICES=<one-physical-GPU-ordinal>
   export MUJOCO_GL=egl
   export PYOPENGL_PLATFORM=egl

   bash tests/e2e_tests/run_gpu_suite.sh \
     <target> \
     /path/to/new-output-dir \
     /path/to/new-venv-root

In an already-installed robot environment, run a single test file or filter directly with ``pytest tests/e2e_tests/<robot> -v -k <expression>``.
