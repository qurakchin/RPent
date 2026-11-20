Installation
============

RPent installs components. Every component declares its own dependencies,
Python support, and hosts in ``component.toml``. ``rpent-install install``
creates the virtual environment, installs the requirements those manifests
resolve to, runs an import probe for each installed component, and writes an
installation fingerprint.

An environment is one virtual environment holding a set of components. It is
named by the sorted join of the requested component names, such as
``infra-dev+robot-libero``; ``install`` without components creates the
core-only ``minimal`` environment. A component's ``requires`` names the
components it runs with, so installing a robot also installs its simulator,
models, and tools.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
  Simulation, model, and robot runtimes target Linux; the installer records the
  host it resolved for, and development environments also install on
  ``darwin-arm64``. ``check --platform`` resolves for another host without
  installing.
- One of the supported Python minors: 3.12, 3.11, or 3.10. Components declare
  the ranges they accept; an environment resolves to the newest supported minor
  that satisfies every component in its closure, and ``rpent-install`` asks uv
  to fetch it when the host does not have it.
- A GPU and driver compatible with the environment's PyTorch build for
  simulator and robot environments.

List components
---------------

.. code-block:: bash

   rpent-install list

The command prints every component with its name, kind, the Python minor its
own environment resolves to, and a description.

A component is named ``<kind>-<directory>``: ``robot``, ``sim``, ``model``,
``tool``, or ``infra``. Every component is an environment under its own name.
``rpent-install install model-sam3`` installs the SAM 3.0 service,
``rpent-install install sim-libero`` installs the LIBERO simulator without a
robot adapter, and ``rpent-install install robot-libero`` installs LIBERO with
the simulator, models, and tools its ``requires`` names.

``python`` in a component is either a version (``"3.11"``) or a range
(``">=3.10,<3.13"``). ``install`` resolves it from the manifests, and ``doctor``
reports when the manifests now resolve to different inputs than the fingerprint
recorded. The host is an installation input too: ``install`` records the host it
resolved for, and ``doctor`` compares it with the host the environment runs on.

Install an environment
----------------------

From a checkout, install a component environment and activate it:

.. code-block:: bash

   rpent-install install robot-libero
   source .venvs/robot-libero/bin/activate

Without ``--venv``, an environment installs into ``.venvs/<environment>`` under
the checkout; ``.venvs/`` is gitignored installation output, so later
``install`` and ``doctor`` runs find the same environment. Pass ``--venv`` to
put an environment elsewhere. Each environment needs its own virtualenv:
environments pin different simulator, robot, and model runtimes, so the
installer refuses to install into a virtualenv that another environment
installed. ``--force`` allows a non-empty virtualenv that belongs to another
tool. ``--dry-run`` runs the same resolution checks and prints the requirements
the environment would install, without creating or changing a virtualenv.

On a fresh checkout the ``rpent-install`` console script does not exist yet.
``./rpent-install.sh`` bootstraps it and passes its arguments to the
installer, so no prior environment is needed:

.. code-block:: bash

   ./rpent-install.sh install robot-libero
   source .venvs/robot-libero/bin/activate

The launcher runs the installer from a throwaway ``uv`` environment that adds
only ``packaging``; it needs ``uv`` on ``PATH`` and nothing else.

``rpent-install`` runs from a checkout. The wheel published to PyPI contains
only the core ``rpent`` package; ``robots/``, ``components/`` with their
``component.toml`` manifests ship only with the source checkout and sdist. A
non-editable ``pip install rpent`` provides the CLI; run a specific robot or
model service from a source checkout, where ``rpent-install`` can find the
manifests.

``install`` resolves the environment from its manifests, so it reads no lock:
changing a manifest changes what the next install creates. The checked-in locks
under ``tests/locks/<environment>.lock`` are optional reproduction artifacts for
rebuilding an environment with exactly the versions a maintainer verified; they
are not installation inputs, and ``install`` and ``check`` work without them.
``python -m tests.tooling.lock <environment>`` regenerates one.

Every environment installs the editable checkout, so a service started from its
own environment imports the checkout it was installed from. A service that
serves other environments is installed as its own environment on the serving
host (``model-openpi`` or ``model-sam3``); callers pass its endpoint at run
time, as shown in :doc:`../guides/flash`. Re-running ``install`` reuses the
virtualenv and repairs a stale installation.

Custom combinations
-------------------

Name several components to compose one environment:

.. code-block:: bash

   rpent-install install robot-franka model-sam3
   source .venvs/model-sam3+robot-franka/bin/activate

The environment is named by the sorted join of the component names, so the
order on the command line does not matter. The fingerprint records the
requested components, and ``doctor`` and ``check`` re-resolve the same
composition, so a component added here stays inside the recorded installation
instead of drifting past it. Pass an environment name, including a
``+``-joined composition, to ``check`` to resolve it without installing.

Resolution checks the whole closure against the indexes the components declare,
so ``env_conflicts``, disagreeing indexes, incompatible Python ranges, and
hosts a component does not support fail before the environment exists;
``install --dry-run`` prints the requirements without installing them.

Components
----------

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - Environment
     - Python
     - Contents
   * - ``minimal``
     - 3.12
     - Core RPent only; verifies the CLI and robot discovery without extra
       components.
   * - ``infra-dev``
     - 3.12
     - Test dependencies for local development and CI.
   * - ``infra-unit_cpu``
     - 3.11
     - CPU-only unit tests: core, the ``infra-dev`` test tools, the CPU Torch
       build, and the CPU flywheel stack.
   * - ``infra-rlinf``
     - 3.12
     - The RLinf release runtime shared by simulator and robot environments.
   * - ``tool-flywheel``
     - 3.11
     - LeRobot trajectory export and replay.
   * - ``sim-libero``
     - 3.12
     - LIBERO and LIBERO-PRO simulation for adapter development, e2e, and data
       collection.
   * - ``sim-libero_plus``
     - 3.12
     - LIBERO-plus simulation tasks for the LIBERO adapter.
   * - ``sim-robocasa``
     - 3.10
     - RoboCasa simulation with RLinf's RoboCasa365 and RLDX stack.
   * - ``sim-robodojo``
     - 3.11
     - RoboDojo simulation and Isaac Sim without a policy or segmentation
       model.
   * - ``sim-robotwin``
     - 3.11
     - RoboTwin simulation with cuRobo and the RLinf runtime.
   * - ``model-molmo``
     - 3.12
     - Molmo visual grounding in a standalone environment.
   * - ``model-openpi``
     - 3.12
     - The Pi0.5 policy runtime.
   * - ``model-sam3``
     - 3.12
     - The SAM 3.0 segmentation runtime.
   * - ``model-rldx``
     - 3.10
     - The RLDX policy runtime for RoboCasa.
   * - ``model-lingbot``
     - 3.11
     - The LingBot-VLA policy runtime for RoboTwin.
   * - ``model-awomo05``
     - 3.11
     - The Awomo05 native joint policy for RoboDojo.
   * - ``model-vpp2``
     - 3.11
     - The VPP2 video-prediction policy for RoboDojo.
   * - ``robot-libero``
     - 3.11
     - LIBERO with Pi0.5, SAM 3.0, and LeRobot trajectory export and replay.
   * - ``robot-franka``
     - 3.12
     - Single-arm Franka with Pi0.5 and the RLinf runtime.
   * - ``robot-dual_franka``
     - 3.12
     - Dual-arm Franka with Pi0.5 and SAM 3.0.
   * - ``robot-yam``
     - 3.11
     - Dual-arm YAM with Pi0.5 and the RLinf runtime.
   * - ``robot-robodojo``
     - 3.11
     - RoboDojo with its RLinf fork and Isaac Sim, Pi0.5, SAM 3.0, Awomo05, and
       VPP2.
   * - ``robot-robocasa``
     - 3.10
     - RoboCasa with RLinf's RoboCasa365 and RLDX stack.
   * - ``robot-robotwin``
     - 3.11
     - RoboTwin with LingBot-VLA and cuRobo.

The remaining components, such as ``model-apxinf``, ``model-cosmos3``, and
``model-uniwam``, install under their own names; ``rpent-install list`` prints
the full set. A robot's row includes the components its ``requires`` names, so
installing it creates one environment with all of them. The Python column shows
the minor the manifests currently resolve to, which can be narrower than the
range a manifest accepts.

Install commands
----------------

Each environment installs with its default virtualenv under
``.venvs/<environment>``. On a fresh checkout, prefix the command as shown
above.

.. code-block:: bash

   rpent-install install
   rpent-install install infra-dev
   rpent-install install infra-unit_cpu
   rpent-install install sim-libero
   rpent-install install sim-libero_plus
   rpent-install install sim-robocasa
   rpent-install install sim-robodojo
   rpent-install install sim-robotwin
   rpent-install install robot-libero
   rpent-install install robot-franka
   rpent-install install robot-dual_franka
   rpent-install install robot-yam
   rpent-install install robot-robodojo
   rpent-install install robot-robocasa
   rpent-install install robot-robotwin
   rpent-install install model-molmo
   rpent-install install model-openpi
   rpent-install install model-sam3

Diagnose
--------

.. code-block:: bash

   rpent-install doctor
   rpent-install doctor --venv .venvs/robot-libero

Without ``--venv``, ``doctor`` inspects the environment activated in the shell,
falling back to the one running ``rpent-install``; the first line names the
environment it inspected. ``doctor`` compares the stored fingerprint with every
installation input (the manifests, the component override files, and the
repository's ``[tool.uv]`` settings), checks Python and platform, runs
``uv pip check`` and the component probes, and prints the fingerprint path and
its SHA-256. ``doctor`` also probes a service installed in another environment
when ``--endpoint <name>=host:port`` or ``RPENT_<NAME>_ENDPOINT`` names its
endpoint, and reports an endpoint it cannot reach. ``uv`` resolves from the
checkout, so the compared settings do not depend on the directory the command is
invoked from; user-level ``uv`` configuration (``~/.config/uv``) is outside the
comparison. The fingerprint records the input mode it was written with, so an
environment installed by an older ``rpent-install`` is reported as needing a
reinstall rather than as drifted.

Run artifacts record the environment name and the fingerprint hash in
``run.json``; the fingerprint itself stays in that environment.

Maintainer checks and reproduction locks
----------------------------------------

``rpent-install check`` resolves environments from their manifests without
installing anything:

.. code-block:: bash

   rpent-install check --all
   rpent-install check minimal --inputs-hash
   rpent-install check robot-robotwin --resolve --platform linux-x86_64

It computes each environment's ``requires`` closure and reports conflicting
requirements, unknown or conflicting components, unsupported Python versions,
and platform mismatches. It downloads nothing and needs no lock. Each
positional argument is an environment name, which may be a ``+``-joined
composition; with none it checks ``minimal``. ``--inputs-hash`` prints the hash
of one environment's installation inputs and the Python minor they resolve to;
CI uses it as the environment cache key. ``--resolve`` additionally compiles
the selected environments with ``uv pip compile`` to prove the declared
dependencies have a solution; it uses the same code path as ``lock`` and reads package
metadata from the configured indexes. ``--platform`` selects the host to
resolve for and defaults to ``linux-x86_64``.

The remaining maintainer tools under ``tests/tooling/`` are not installed with
the wheel. Run them from a checkout through ``tests/tooling/run.sh``,
which passes the module and its arguments to a throwaway ``uv`` environment:

.. code-block:: bash

   tests/tooling/run.sh rpent.cli.install check --all
   tests/tooling/run.sh tests.tooling.lock sim-robotwin
   tests/tooling/run.sh tests.tooling.lock --all --check

``lock`` compiles an environment's reproduction lock with ``uv pip compile`` and
records the upstream cutoff as an ``# exclude_newer`` header. Locks live under
``tests/locks/<environment>.lock`` and change nothing about what ``install``
does. ``--check`` recompiles at that recorded instant and fails when the result
differs from the committed lock, so it reports changed manifests or a different
resolver rather than packages released since. ``lock --all`` reports an
environment that cannot resolve on the current host and continues with the
rest; the ``sim-robotwin`` lock needs a Linux host with ``CUDA_HOME`` set
because cuRobo builds metadata during resolution. Linux locks target the
``manylinux_2_31`` baseline by default (glibc 2.31, Ubuntu 20.04 or newer),
because current GPU wheels are not published for older baselines. The closure
uses the newest baseline any of its components declares; for example
``sim-robodojo`` declares ``manylinux = "2_35"`` for Isaac Sim 5.1 wheels.
Regenerate locks with the ``uv`` release that generated them (0.13.7): an older
release can resolve different versions for the same inputs. The release job
pins that version; bump both together in a relock change.

The other maintainer tools cover repository structure and CI selection:
``python -m tests.tooling.layout`` checks component boundaries, and
``python -m tests.tooling.matrix`` and ``python -m tests.tooling.affected``
select and partition environments. CI runs them with the same ``uv run``
bootstrap shown above.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
