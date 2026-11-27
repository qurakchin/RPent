Testing and CI
==============

GitHub runs CPU unit tests and reports line coverage in the test logs.
On PR updates and pushes to ``main``, **Simulator CI** automatically selects
affected GPU end-to-end suites from the changed paths, installs each component
into a fresh virtual environment with ``rpent-install.sh``, and runs its
suite. For example, RLDX changes trigger RoboCasa, shared planner changes
trigger all seven suites, and documentation-only changes skip simulator CI.

Each selected GPU suite exercises every advertised tool one at a time through
the public CLI and ends by calling ``finish``.

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
     - Declarative GPU end-to-end suites under ``suites/*.toml`` driven by a shared runner (``run_gpu_suite.sh``) that exercises every advertised tool through the public CLI.

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

2. **GPU end-to-end suite** (add ``tests/e2e_tests/suites/<name>.toml``; see ``robocasa.toml`` or ``libero.toml`` in the same directory for examples):

   CI discovers ``suites/*.toml`` automatically without workflow or script changes. Fill in the fields you need:

   - **Required**: Set ``component`` to the install component name (for example ``robot-robocasa``), and add one ``[[cases]]`` entry per action-model backend with its ``name`` and CLI ``args``.
   - **Shared options**: Put flags shared across cases in ``base_args`` and default environment variables in ``env`` (already-exported environment variables override defaults).
   - **Paths and skips**: Write relative paths under ``assets/``, ``models/``, or ``venvs/``; they resolve automatically against the shared resource root, and ``{gpu}`` expands to the selected GPU index. A case is skipped automatically if any of its required paths is missing (the suite fails if every case is skipped).
   - **Action checks (recommended)**: Set ``action_tool`` and ``action_count_field`` to confirm real simulator steps ran; set ``require_post_action_image = true`` when the next turn must receive a new image; use ``tool_args`` when specific tools need concrete sample arguments.
   - **Special setup or external services (when needed)**: Use ``[setup]`` (``post_install_cmd``, plus ``materialize_pkgs`` or ``reinstall_copy_pkg`` when package files must be copied out of the shared cache) for post-install asset linking or editable dependencies, and ``[cases.sidecar]`` when a case must launch a local service before connecting via an endpoint.

See :doc:`add_robot` for the full robot integration guide.

Adding a Model
~~~~~~~~~~~~~~

When adding an action model or perception model under ``components/models/<name>/``:

1. **Offline CPU unit tests** under ``tests/unit_tests/components/models/`` (and ``tests/unit_tests/robots/<robot>/`` for robot-specific adapters):

   - Verify configuration validation, startup arguments, and observation/action format conversion.
   - Verify local HTTP/socket communication with a lightweight test backend, including session isolation, reset, error handling, and worker shutdown.

2. **GPU end-to-end case** in each supported robot's ``tests/e2e_tests/suites/<robot>.toml``:

   - Add a ``[[cases]]`` entry with the backend's CLI arguments and relative resource paths under the shared root.
   - Missing checkpoints, interpreters, or endpoints automatically skip only that case without failing the rest of the suite.

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

In an already-installed robot environment, run a single suite or case directly with ``RPENT_E2E_SUITE=<target> pytest tests/e2e_tests/test_suites.py -v -k <expression>``.
