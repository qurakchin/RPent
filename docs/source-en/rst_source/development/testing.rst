Testing and CI
==============

RPent verifies changes across four layers: offline CPU unit tests, repository layout checks, simulator environment builds (with or without cache), and GPU end-to-end tests. This page explains how to trigger CI on GitHub, how ``tests/`` is organized, what tests to add for a new robot or model, and how to run tests locally.

Trigger CI on GitHub
--------------------

.. list-table::
   :header-rows: 1
   :widths: 28 32 40

   * - Workflow
     - Trigger
     - Coverage
   * - **Unit tests and layout**
     - Automatic on push and PR
     - Offline CPU unit tests, coverage, package check, and repository layout check
   * - **Simulator environment builds**
     - **Actions → Run workflow** or PR comment ``/ci-build``
     - Fresh virtualenv installation per simulator component (default cached build, or cold install with ``no_cache`` / ``--no-cache``), plus ``rpent-install.sh doctor`` and ``rpent --help``
   * - **Embodied GPU E2E**
     - **Actions → Run workflow** or PR comment ``/ci-all`` / ``/ci-<target>``
     - Clean environment installation plus simulator smoke, model component, and scripted CLI end-to-end tests

Simulator Environment Builds
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PR comments require repository maintainer permissions.

- **Manual**: Open **Actions → Simulator environment builds → Run workflow**, pick ``component`` (``all`` or one of ``robot-libero``, ``robot-libero_plus``, ``robot-robocasa``, ``robot-robotwin``, ``robot-robodojo``, ``robot-robolab``), and check ``no_cache`` for a cold install from scratch.
- **PR comment**: Comment ``/ci-build`` (or ``/ci-build-all``) for all components, or ``/ci-build-<component>`` for one component. Append ``--no-cache`` for a cold install. Examples:

  - ``/ci-build``
  - ``/ci-build-robot-libero``
  - ``/ci-build-robot-libero --no-cache``

Embodied GPU E2E
~~~~~~~~~~~~~~~~

PR comments require repository maintainer permissions.

- **Manual**: Open **Actions → Embodied GPU E2E → Run workflow** and pick ``target`` (``all``, ``libero``, ``libero-pro``, ``libero-plus``, ``robocasa``, ``robotwin``, ``robodojo``, or ``robolab``).
- **PR comment**: Comment ``/ci-all`` for all simulator suites, or ``/ci-<target>`` for one suite. Examples:

  - ``/ci-all``
  - ``/ci-libero``
  - ``/ci-robocasa``

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
   - **Scripted CLI chain** (``test_policy_chain.py``): call ``run_scripted_policy_chain`` with the local scripted planner (no external LLM API required) to exercise the public CLI, verify saved outputs, and confirm all background processes exit.

3. **CI registration**:

   - Add a target to ``tests/e2e_tests/run_gpu_suite.sh`` and register it in the **Embodied GPU E2E** workflow.
   - If the integration adds an installable ``robot-<name>`` component, also register it in the **Simulator environment builds** workflow.

See :doc:`add_robot` for the full robot integration guide.

Adding a Model
~~~~~~~~~~~~~~

When adding an action model or perception model under ``components/models/<name>/``:

1. **Offline CPU unit tests** under ``tests/unit_tests/components/models/`` (and ``tests/unit_tests/robots/<robot>/`` for robot-specific adapters):

   - Verify configuration validation, startup arguments, and observation/action format conversion.
   - Verify local HTTP/socket communication with a lightweight test backend, including session isolation, reset, error handling, and worker shutdown.

2. **GPU end-to-end cases** in each supported robot's ``tests/e2e_tests/<robot>/``:

   - Add a model inference case in ``test_components.py`` and a scripted CLI case in ``test_policy_chain.py``.
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
