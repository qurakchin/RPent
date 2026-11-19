Installation
============

RPent installs a named environment profile, not a list of extras. Each profile
selects components and where they live; every component declares its own
dependencies in ``component.toml``. ``rpent-install`` creates the virtual
environment, installs exactly the profile's lock, runs an import probe for each
component it installs locally, and writes an installation fingerprint.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
- The Python minor version named by the profile. ``rpent-install`` asks uv to
  fetch it when the host does not have it.
- A GPU and driver compatible with the profile's PyTorch build for simulator
  and robot profiles.

List profiles
-------------

.. code-block:: bash

   rpent-install list

The command prints every component with its kind and placements, then every
profile with its Python version and components.

Profiles live in ``installs/profiles/``. Test and development environments
(``dev``, ``unit-cpu``, ``tool-geometry``) live in ``tests/profiles/``; both
directories are discovered as one namespace, and a name declared twice is
rejected. Names follow ``<kind>-<name>[_<variant>]``, where ``kind`` is
``sim``, ``real``, ``model``, ``tool``, or ``robot``; the name copies the
component and keeps its underscores, and a variant selects one of the
component's option groups (``sim-libero_pro``). ``minimal``, ``dev``, and
``unit-cpu`` keep their historical names.

A ``robot-`` profile is a compound environment: it installs one simulator or
robot with the models that target uses. Profiles do not reference each other,
so a combination the repository does not name is installed as separate
``sim-``, ``real-``, ``model-``, or ``tool-`` environments and connected at run
time with endpoints.

Install a profile
-----------------

From a checkout, install a profile and activate its environment:

.. code-block:: bash

   rpent-install install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

Without ``--venv``, a profile installs into ``.venvs/<profile>`` under the
checkout; ``.venvs/`` is gitignored installation output, so later ``install``
and ``doctor`` runs find the same environment. Pass ``--venv`` to put an
environment elsewhere. Each profile needs its own environment: profiles pin
different simulator, robot, and model runtimes, so the installer refuses to
install into an environment that another profile installed. ``--force``
allows a non-empty environment that records no fingerprint.

On a fresh checkout the ``rpent-install`` console script does not exist yet.
Bootstrap it without installing RPent first:

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.install install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

``rpent-install`` runs from a checkout. The wheel published to PyPI contains
only the core ``rpent`` package; ``robots/``, ``components/`` with their
``component.toml`` manifests, and ``installs/profiles/`` ship only with the
source checkout and sdist. A non-editable ``pip install rpent`` provides the
CLI; run a specific robot, model service, or toolkit from a source checkout,
where ``rpent-install`` can find the profiles.

Every profile is installed from a lock. User profiles keep theirs in
``installs/locks/<profile>.lock`` and test profiles in
``tests/locks/<profile>.lock``; a profile may also name its lock explicitly.
Before installing, the installer checks that the lock exists and still covers
every direct requirement and component override. A missing or stale lock fails
with the command that regenerates it:
``python -m tests.tooling.lock <profile>``.

A profile with ``core = false``, such as ``model-molmo``, skips the editable
RPent install and contains only that service's dependencies; start it with the
checkout on ``PYTHONPATH`` as shown in :doc:`../guides/flash`. A component
placed remotely installs only its client side; install the ``model-*`` profile
that runs the service on the serving host and pass its endpoint at run time.
Re-running ``install`` reuses the environment and repairs a stale installation.

Profiles
--------

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - Profile
     - Python
     - Contents
   * - ``minimal``
     - 3.11
     - Core RPent only; verifies the CLI and robot discovery without extras.
   * - ``dev``
     - 3.10
     - Test dependencies for local development and CI.
   * - ``unit-cpu``
     - 3.10
     - CPU-only unit tests: core, test tools, the CPU Torch build, and the
       CPU flywheel stack.
   * - ``sim-libero_standard``
     - 3.11
     - LIBERO simulation with the RLinf runtime for adapter development, e2e,
       and data collection.
   * - ``sim-libero_pro``
     - 3.11
     - LIBERO-PRO simulation, same scope as ``sim-libero_standard``.
   * - ``sim-libero_plus``
     - 3.11
     - LIBERO-plus simulation, same scope as ``sim-libero_standard``.
   * - ``sim-robocasa``
     - 3.10
     - RoboCasa simulation with RLinf's RoboCasa365 and RLDX stack.
   * - ``sim-robotwin``
     - 3.11
     - RoboTwin simulation with LingBot-VLA and cuRobo.
   * - ``sim-robodojo``
     - 3.11
     - RoboDojo with its RLinf fork and Isaac Sim, without a policy or
       segmentation model.
   * - ``real-franka`` / ``real-dual_franka``
     - 3.11
     - Franka hardware and platform dependencies without a policy model.
   * - ``real-yam``
     - 3.11
     - Dual-arm YAM control dependencies without a policy model.
   * - ``robot-libero_pro``
     - 3.11
     - LIBERO-PRO with Pi0.5, SAM 3.0, and LeRobot trajectory export and
       replay.
   * - ``robot-franka``
     - 3.11
     - Single-arm Franka with Pi0.5.
   * - ``robot-dual_franka``
     - 3.11
     - Dual-arm Franka with Pi0.5 and SAM 3.0.
   * - ``robot-yam``
     - 3.11
     - Dual-arm YAM with Pi0.5.
   * - ``robot-robodojo``
     - 3.11
     - RoboDojo with its RLinf fork and Isaac Sim, Pi0.5, and SAM 3.0.
   * - ``model-molmo``
     - 3.11
     - Standalone Molmo visual grounder (``core = false``).
   * - ``model-openpi`` / ``model-sam3``
     - 3.11
     - Single-capability diagnostic environments.
   * - ``tool-flywheel``
     - 3.11
     - LeRobot trajectory export and replay without a simulator or policy.
   * - ``tool-geometry``
     - 3.11
     - Geometry toolkit with its frozen CPU evaluation corpus.

Install commands
----------------

Each profile installs with its default environment under ``.venvs/<profile>``.
On a fresh checkout, prefix the command as shown above.

.. code-block:: bash

   rpent-install install minimal
   rpent-install install dev
   rpent-install install unit-cpu
   rpent-install install sim-libero_standard
   rpent-install install sim-libero_pro
   rpent-install install sim-libero_plus
   rpent-install install sim-robocasa
   rpent-install install sim-robotwin
   rpent-install install sim-robodojo
   rpent-install install real-franka
   rpent-install install real-dual_franka
   rpent-install install real-yam
   rpent-install install robot-libero_pro
   rpent-install install robot-franka
   rpent-install install robot-dual_franka
   rpent-install install robot-yam
   rpent-install install robot-robodojo
   rpent-install install model-molmo
   rpent-install install model-openpi
   rpent-install install model-sam3
   rpent-install install tool-flywheel
   rpent-install install tool-geometry

Diagnose
--------

.. code-block:: bash

   rpent-install doctor
   rpent-install doctor --venv .venvs/robot-libero_pro

Without ``--venv``, ``doctor`` inspects the active virtual environment.
``--profile`` overrides the profile recorded in the fingerprint. ``doctor``
compares the stored fingerprint with every recorded installation input (the
manifests, the lock the install read, the component override files, and the
repository's ``[tool.uv]`` settings), checks Python and platform, runs
``uv pip check`` and the component probes, and prints the fingerprint path and
its SHA-256. Components placed remotely are probed with
``--endpoint <name>=host:port`` or ``RPENT_<NAME>_ENDPOINT``; a remote component
without an endpoint is reported as a warning. ``uv`` resolves from the
checkout, so the
compared settings do not depend on the directory the command is invoked from;
user-level ``uv`` configuration (``~/.config/uv``) is outside the comparison.
The fingerprint records the input mode it was written with, so an environment
installed by an older ``rpent-install`` is reported as needing a reinstall
rather than as drifted.

Run artifacts record the active profile, fingerprint hash, source commit, and
component names in ``run.json``.

Maintainer checks and locks
---------------------------

The repository checks and lock generation are maintainer tools under
``tests/tooling/``; they are not installed with the wheel and are not part of
``rpent-install``. Run them from a checkout:

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.check --all
   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.lock sim-robotwin
   uv run --no-project --python 3.11 --with packaging -- \
     python -m tests.tooling.lock --all --check

``check`` reads manifests and profiles, computes each profile's ``requires``
closure, and reports conflicting placements, duplicate pins, unsupported
Python versions, platform mismatches, and locks that no longer cover the
requirements. It downloads nothing. ``--resolve`` additionally compiles every
profile with ``uv pip compile`` to prove the declared dependencies have a
solution; it uses the same code path as ``lock`` and reads package metadata
from the configured indexes.

``lock`` compiles each profile's lock with ``uv pip compile`` and records the
upstream cutoff as an ``# exclude_newer`` header. ``--check`` recompiles at
that recorded instant and fails when the result differs from the committed
lock, so it reports changed manifests or a different resolver rather than
packages released since. ``lock --all`` reports a profile that cannot resolve
on the current host and continues with the rest; the ``sim-robotwin`` lock
needs a Linux host with ``CUDA_HOME`` set because cuRobo builds metadata during
resolution. Linux locks target the ``manylinux_2_31`` baseline by default
(glibc 2.31, Ubuntu 20.04 or newer), because current GPU wheels are not
published for older baselines. A profile whose components need a newer
baseline sets ``manylinux``; for example ``robot-robodojo`` uses
``manylinux = "2_35"`` for Isaac Sim 5.1 wheels. Regenerate locks with the
``uv`` release that generated them (0.13.7): an older release can resolve
different versions for the same inputs. The release job pins that version;
bump both together in a relock change.

The other maintainer tools cover repository structure and CI selection:
``python -m tests.tooling.layout`` checks component boundaries,
``python -m tests.tooling.extras --check`` checks the generated extras, and
``python -m tests.tooling.matrix`` and ``python -m tests.tooling.affected``
select and partition test environments. CI runs them with the same ``uv run``
bootstrap shown above.

Compatibility extras
--------------------

``python -m tests.tooling.extras`` generates the ``[tool.rpent.extras]`` and
``[tool.uv].conflicts`` tables in ``pyproject.toml`` from the same manifests
and profiles. ``setup.py`` passes the extras table to ``extras_require`` for
source and editable installs, so ``pip install -e ".[libero-pro]"`` keeps
working for one release; the published core wheel carries no extras. Do not
edit the generated block by hand. ``--check`` fails when the block is stale.
Profiles are the supported interface; use extras only for migration.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
