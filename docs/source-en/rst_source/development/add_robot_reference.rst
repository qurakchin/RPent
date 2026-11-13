Robot Integration Reference
===========================

Runner hooks, runtime startup, and test coverage for a new robot integration.
The integration steps are in :doc:`add_robot`.

.. page-head::
   :for: Developers who need the runner hooks, runtime startup, or test coverage for an integration
   :outcome: You can implement the CLI and config hooks and runtime startup, and decide which tests to add
   :read-when: The integration steps in :doc:`add_robot` point here, or runtime startup fails
   :skip-when: You have not read the integration steps; start with :doc:`add_robot`

**Page map:** runner hooks → runtime initialization → run-result finalizer → test details.

.. _add-robot-config:

Runner Hooks
-------------------------------------------------------

Robot-specific CLI arguments enter ``rpent/cli/main.py`` through two
hooks and participate in the final argparse pass:

**``_add_cli_args(parser, use_dashboard) -> None``.** Register the
robot's arguments on the shared parser created by main.py.
``use_dashboard`` determines whether normally required arguments remain
optional. For each Dashboard TaskRun, the robot's Dashboard task command
supplies the fields declared by its spec before ``parse_config`` runs. main.py
calls this hook before ``parser.parse_args()``, so argparse's usage and error
output includes the robot arguments.

**``_parse_config(args) -> RunConfig``.** In normal CLI mode, this is called
after ``parser.parse_args()``. In Dashboard mode, it is called for each
TaskRun after the requested fields have been copied to the task arguments. It
validates those fields and returns a
:class:`~rpent.robots.RunConfig`:

- ``recipe_tag`` — robot's per-run tag, used in transcript filenames / recipe
  path (LIBERO: ``f"{suite.replace('libero_', '')}_t{task}_s{seed}"``).
- ``output_dir`` — path to the working directory for this run (main.py then
  calls ``init_output_dir`` to create it and configure logging).
- ``prompt_vars`` — dict passed to ``PromptBundle.render`` (typically the run
  identifiers plus anything else the prompts reference).
- ``task_desc`` — robot-specific dict of task-identifying fields, written into
  the transcript JSON record verbatim (LIBERO:
  ``{"suite": ..., "task": ..., "seed": ...}``).

.. code-block:: python

   def _add_cli_args(parser, use_dashboard) -> None:
       required = not use_dashboard
       parser.add_argument("--suite", default=None, required=required)
       parser.add_argument("--task", type=int, default=None, required=required)
       # ... other robot-specific flags ...

   def _parse_config(args) -> RunConfig:
       if not args.suite: raise ValueError("--suite is required")
       # ... derive recipe_tag, output_dir, and prompt_vars ...
       return RunConfig(
           recipe_tag=recipe_tag,
           output_dir=output_dir,
           prompt_vars=prompt_vars,
           task_desc={"suite": args.suite, "task": args.task, "seed": args.seed},
       )

.. _add-robot-runtime:

Runtime Initialization
------------------------------

``init_runtime`` returns ``(owned_daemons, runtime_kwargs)``:

- ``owned_daemons: list[ProcessDaemon]`` contains only subprocesses started
  by this process. The active runner stops them during cleanup. A client for an
  external endpoint must not add that external service to this list.
- ``runtime_kwargs: dict`` is passed to the toolkit constructor, which
  forwards it to the primitives' ``__init__``. A complete set commonly
  contains ``{"env": MyEnvClient(...), "model": VLAClient(...)}`` plus any
  supporting clients.

The fourth argument, ``components``, selects which named services to
initialize. ``None`` means all services and is what the normal CLI passes.
The Dashboard derives two subsets from ``dashboard.runtime_components``. Every
component declares either ``scope: "shared"`` or ``scope: "unique"`` explicitly.
The Dashboard initializes shared components once, then initializes unique
components for every fresh environment instance. It calls this same hook for
both subsets and merges the returned ``runtime_kwargs`` dictionaries. For
LIBERO, the subsets are ``{"vla", "sam3"}`` and ``{"env"}``.

An implementation should reject unknown component names before starting
anything. When several selected local services are expensive to initialize,
start them all before waiting for readiness so their initialization can
overlap. See ``robots/libero/robot_spec.py`` for the ordered component registry
used by the reference implementation.

Endpoint parsing (``--env-endpoint``, ``--am-endpoint``, and LIBERO's
``--sam3-endpoint``) and robot-specific server commands belong in the
hook that owns the corresponding service. Wrap those spawners with
``rpent.robots.runtime.try_spawn_server`` and ``try_wait_server`` so status
events, readiness failures, and owned-daemon cleanup stay consistent across
robots. The runners do not handle these environment details. See
``robots/libero/robot_spec.py`` and ``robots/robocasa/robot_spec.py`` for the
reference pattern.

Optional Run-result Finalizer
-----------------------------

``RobotSpec.finalize_run`` is a universal, robot-agnostic end-of-run hook.
RoboCasa, RoboDojo, and YAM register it to record per-cell evaluation results
for later statistics and aggregation. Any robot that publishes machine-readable
evaluation artifacts may register the hook. The default is ``None`` and leaves
the runner unchanged. When the hook is present, both the terminal runner and
the Dashboard capture ``toolkit.solved()`` before closing the toolkit, then
pass a structured ``RunFinalizationContext`` to the hook after runtime
cleanup. The hook owns the artifact schema and filename; RPent only defines the
lifecycle boundary.

Use ``write_json_atomic`` when the artifact is JSON so an interrupted write
cannot leave a partial result:

.. code-block:: python

   from rpent.evaluation import RunFinalizationContext, write_json_atomic

   def _finalize_run(context: RunFinalizationContext):
       return write_json_atomic(
           context.output_dir / "result.json",
           {
               "robot": context.robot_name,
               "task": dict(context.task_desc),
               "success": context.environment_success,
           },
       )

Register the callback as ``RobotSpec(..., finalize_run=_finalize_run)``. This
hook is currently limited to normal terminal runs; the Dashboard also calls
it. Keep benchmark manifests, robot-specific runtime fields, and aggregation
logic in the robot package rather than the shared CLI.

Test Details
------------

Test Locations
~~~~~~~~~~~~~~

Use ``myrobot`` below for the new robot's package name:

- ``tests/unit_tests/robots/myrobot/``: offline tests for configuration,
  client argument handling, tool dispatch, and runtime startup/cleanup logic.
  Use fakes for simulators and models so these tests run on CPU.
- ``tests/e2e_tests/myrobot/test_components.py``: one named test per real
  component, such as ``test_environment_component``, ``test_pi05_component``,
  and ``test_sam3_component``. Include only the components the robot uses.
- ``tests/e2e_tests/myrobot/test_policy_chain.py``: one test connecting the
  planner, toolkit, model, and environment.
- Keep fixtures in the same directory's ``conftest.py`` and reusable scenario
  setup/calls in ``scenario.py``. Reuse lifecycle and assertion helpers from
  ``tests/e2e_tests/common.py``. See ``tests/e2e_tests/libero/`` for an example.

What Each Component Test Should Check
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Env:** start the real environment, reset a fixed task/seed, and read an
  observation. Check required camera images and state fields, including their
  shapes and dtypes. Execute at least one valid action and check the next
  observation and termination/success information.
- **VLA or other action model:** load a real checkpoint and perform one
  prediction using an observation and instruction in the robot's input format.
  Check that the returned actions are nonempty, finite, and have the expected
  dimensions for this environment.
- **Perception or other services:** call each service with a known input and
  validate its output. For example, ask SAM3 to segment a known object and
  check that the mask matches the image dimensions and contains foreground.

Start each component through the supported runtime interface, and verify that
its owned daemons exit after the test. Existing tests may cover a reused
component; identify that coverage and test any new input/output adaptation.

Complete Policy-chain Test
~~~~~~~~~~~~~~~~~~~~~~~~~~

After component tests pass, use ``run_scripted_policy_chain`` from
``tests/e2e_tests/common.py`` to run the public CLI with a fixed task/seed and
bounded action count. Its local ``OfflinePlannerServer`` requests a real
action primitive followed by ``finish``, without an external LLM API. Keep the
environment and model services real; do not monkeypatch CLI or runtime internals.

Check that at least one environment action was executed, ``finish`` was
recorded in the transcript, ``states.json`` contains the action without
errors, expected observation artifacts exist, and owned daemons have exited.
Task success is not required for this bounded integration check.

Run offline tests with ``pytest tests/unit_tests/robots/myrobot -v``. After
installing the robot extra and preparing its GPU/checkpoint/assets resources,
run ``pytest tests/e2e_tests/myrobot -v``. See ``tests/README.md`` and
``tests/e2e_tests/run_gpu_suite.sh`` for running GPU suites in clean environments.
