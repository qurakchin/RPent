Installation
============

RPent installs a named target, not a list of extras. A target selects
components and where they live; every component declares its own dependencies
and Python support in ``component.toml``. ``rpent-install`` creates the virtual
environment, installs the requirements those manifests resolve to, runs an
import probe for each component it installs locally, and writes an installation
fingerprint.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
  Other hosts are rejected before anything is installed.
- One of the supported Python minors: 3.12, 3.11, or 3.10. The target resolves
  to one of them and ``rpent-install`` asks uv to fetch it when the host does
  not have it.
- A GPU and driver compatible with the target's PyTorch build for simulator
  and robot targets.

List targets
-------------

.. code-block:: bash

   rpent-install list

The command prints every component with its kind and placements, then every
target with its Python request and components.

Every non-robot component is installable under its own name: ``rpent-install
install sam3`` installs the SAM 3.0 service component and its dependencies.
Robots install only through a target, which names the environment the robot
runs in. Targets declared in ``installs/targets/`` or ``tests/targets/`` add
the compositions a single component cannot express: several components in one
environment, a selected variant, extra runtime dependencies, or a
compatibility extra. The two directories are discovered as one namespace, and
an explicit target may not reuse a component name; the one exception is a
robot's same-name override target, which must install that robot. Test and
development targets (``dev``, ``unit-cpu``, ``tool-geometry-eval``) live in
``tests/targets/``.

Compound targets install one simulator or robot with the models it runs, for
example ``robot-libero_pro`` (LIBERO-PRO with Pi0.5 and SAM 3.0) and
``robot-yam`` (YAM with Pi0.5). Targets do not reference each other, so a
combination the repository does not name is installed as separate component
environments and connected at run time with endpoints.

``python`` in a component or target is either a version (``"3.11"``) or a
range (``">=3.10,<3.13"``). A range resolves to the newest supported minor that
satisfies the target and every component in its closure, so widening support
does not by itself change an installed environment. ``install`` resolves the
minor from the manifests, and ``doctor`` reports when the manifests now resolve
to different inputs than the fingerprint recorded.

Install a target
-----------------

From a checkout, install a target and activate its environment:

.. code-block:: bash

   rpent-install install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

Without ``--venv``, a target installs into ``.venvs/<target>`` under the
checkout; ``.venvs/`` is gitignored installation output, so later ``install``
and ``doctor`` runs find the same environment. Pass ``--venv`` to put an
environment elsewhere. Each target needs its own environment: targets pin
different simulator, robot, and model runtimes, so the installer refuses to
install into an environment that another target installed. ``--force``
allows a non-empty environment that records no fingerprint.
``--dry-run`` runs the same resolution checks and prints the requirements the
target would install, without creating or changing an environment.

On a fresh checkout the ``rpent-install`` console script does not exist yet.
``./rpent-install.sh`` bootstraps it and passes its arguments to the
installer, so no prior environment is needed:

.. code-block:: bash

   ./rpent-install.sh install robot-libero_pro
   source .venvs/robot-libero_pro/bin/activate

The launcher runs the installer from a throwaway ``uv`` environment that adds
only ``packaging``; it needs ``uv`` on ``PATH`` and nothing else.

``rpent-install`` runs from a checkout. The wheel published to PyPI contains
only the core ``rpent`` package; ``robots/``, ``components/`` with their
``component.toml`` manifests, and ``installs/targets/`` ship only with the
source checkout and sdist. A non-editable ``pip install rpent`` provides the
CLI; run a specific robot, model service, or toolkit from a source checkout,
where ``rpent-install`` can find the targets.

``install`` resolves the target from its manifests, so it reads no lock:
changing a manifest changes what the next install creates. The checked-in locks
under ``tests/locks/<target>.lock`` are optional reproduction artifacts for
rebuilding an environment with exactly the versions a maintainer verified; they
are not installation inputs, and ``install`` and ``check`` work without them.
``python -m tests.tooling.lock <target>`` regenerates one.

A target with ``core = false``, such as ``molmo``, skips the editable
RPent install and contains only that service's dependencies; start it with the
checkout on ``PYTHONPATH`` as shown in :doc:`../guides/flash`. A component
placed remotely installs only its client side; install the same component
(``openpi`` or ``sam3``) as a local target on the serving host and pass its
endpoint at run time. Re-running ``install`` reuses the environment and
repairs a stale installation.

Custom combinations
-------------------

A combination the repository does not name is a target file, not a list of
names on the command line. ``install`` accepts one target because the target is
what resolution, the fingerprint, and later ``doctor`` runs describe; a set of
components joined on the fly would have no record to compare against.

Create the file under ``installs/targets/`` with the name it installs under,
then install it:

.. code-block:: toml

   schema = 2
   kind = "target"
   name = "my-combo"
   python = "3.11"

   [components.franka]

   [components.sam3]

.. code-block:: bash

   ./rpent-install.sh install my-combo

An empty component table takes that component's default placement;
``placement = "remote"`` installs only the client side of a service, and a
component that requires a variant, such as ``libero``, must name one.
Resolution checks the whole closure against the indexes the components declare,
so ``env_conflicts``, disagreeing indexes, and incompatible Python ranges fail
before the environment exists; ``install --dry-run`` prints the requirements
without installing them.

Targets
-------

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - Target
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
   * - ``robot-robocasa``
     - 3.10
     - RoboCasa simulation with RLinf's RoboCasa365 and RLDX stack.
   * - ``robot-robotwin``
     - 3.11
     - RoboTwin simulation with LingBot-VLA and cuRobo.
   * - ``molmo``
     - 3.11
     - Standalone Molmo visual grounder (``core = false``).
   * - ``openpi`` / ``sam3``
     - 3.11
     - Single-capability diagnostic environments.
   * - ``tool-flywheel``
     - 3.11
     - LeRobot trajectory export and replay without a simulator or policy.
   * - ``tool-geometry-eval``
     - 3.11
     - Geometry toolkit with its frozen CPU evaluation corpus.

The remaining non-robot components (``apxinf``, ``cosmos3``, ``cosmos_policy``,
``fast_wam``, ``geometry``, ``uniwam``, and ``xpolicylab``) install under their
own names as well; ``rpent-install list`` prints the full set. The Python column
shows the minor the manifests currently resolve to, which can be narrower than
the range a manifest accepts.

Install commands
----------------

Each target installs with its default environment under ``.venvs/<target>``.
On a fresh checkout, prefix the command as shown above.

.. code-block:: bash

   rpent-install install minimal
   rpent-install install dev
   rpent-install install unit-cpu
   rpent-install install sim-libero_standard
   rpent-install install sim-libero_pro
   rpent-install install sim-libero_plus
   rpent-install install robot-libero_pro
   rpent-install install robot-franka
   rpent-install install robot-dual_franka
   rpent-install install robot-yam
   rpent-install install robot-robodojo
   rpent-install install robot-robocasa
   rpent-install install robot-robotwin
   rpent-install install molmo
   rpent-install install openpi
   rpent-install install sam3
   rpent-install install tool-flywheel
   rpent-install install tool-geometry-eval

Diagnose
--------

.. code-block:: bash

   rpent-install doctor
   rpent-install doctor --venv .venvs/robot-libero_pro

Without ``--venv``, ``doctor`` inspects the environment activated in the shell,
falling back to the one running ``rpent-install``; the first line names the
environment it inspected. ``--target`` overrides the target recorded in the
fingerprint and reports the mismatch as a warning. ``doctor`` compares the
stored fingerprint with every installation input (the manifests, the component
override files, and the repository's ``[tool.uv]`` settings), checks Python and
platform, runs ``uv pip check`` and the component probes, and prints the
fingerprint path and its SHA-256. Components placed remotely are probed with
``--endpoint <name>=host:port`` or ``RPENT_<NAME>_ENDPOINT``; a remote component
without an endpoint is reported as a warning. ``uv`` resolves from the
checkout, so the
compared settings do not depend on the directory the command is invoked from;
user-level ``uv`` configuration (``~/.config/uv``) is outside the comparison.
The fingerprint records the input mode it was written with, so an environment
installed by an older ``rpent-install`` is reported as needing a reinstall
rather than as drifted.

Run artifacts record the installed target and the fingerprint hash in
``run.json``; the fingerprint itself stays in that environment.

Maintainer checks and reproduction locks
----------------------------------------

The repository checks and lock generation are maintainer tools under
``tests/tooling/``; they are not installed with the wheel and are not part of
``rpent-install``. Run them from a checkout through ``tests/tooling/rpent-tool.sh``,
which passes the module and its arguments to a throwaway ``uv`` environment:

.. code-block:: bash

   tests/tooling/rpent-tool.sh tests.tooling.check --all
   tests/tooling/rpent-tool.sh tests.tooling.check minimal --inputs-hash
   tests/tooling/rpent-tool.sh tests.tooling.lock robotwin
   tests/tooling/rpent-tool.sh tests.tooling.lock --all --check

``check`` reads manifests and targets, computes each target's ``requires``
closure, and reports conflicting placements, duplicate pins, unsupported
Python versions, platform mismatches, and repository data that disagrees with
the manifests. It downloads nothing and needs no lock. ``--inputs-hash`` prints
the hash of one target's installation inputs and the Python minor they resolve
to; CI uses it as the environment cache key. ``--resolve`` additionally
compiles every target with ``uv pip compile`` to prove the declared
dependencies have a solution; it uses the same code path as ``lock`` and reads
package metadata from the configured indexes.

``lock`` compiles a target's reproduction lock with ``uv pip compile`` and
records the upstream cutoff as an ``# exclude_newer`` header. Locks live under
``tests/locks/<target>.lock`` and change nothing about what ``install`` does.
``--check`` recompiles at that recorded instant and fails when the result
differs from the committed lock, so it reports changed manifests or a different
resolver rather than packages released since. ``lock --all`` reports a target that cannot resolve
on the current host and continues with the rest; the ``robotwin`` lock
needs a Linux host with ``CUDA_HOME`` set because cuRobo builds metadata during
resolution. Linux locks target the ``manylinux_2_31`` baseline by default
(glibc 2.31, Ubuntu 20.04 or newer), because current GPU wheels are not
published for older baselines. A target whose components need a newer
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
and targets. ``setup.py`` passes the extras table to ``extras_require`` for
source and editable installs, so ``pip install -e ".[libero-pro]"`` keeps
working for one release; the published core wheel carries no extras. Do not
edit the generated block by hand. ``--check`` fails when the block is stale.
Targets are the supported interface; use extras only for migration.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
