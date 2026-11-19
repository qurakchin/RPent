Installation
============

RPent installs a named target. A target selects components; every component
declares its own dependencies, Python support, and hosts in ``component.toml``.
``rpent-install`` creates the virtual environment, installs the requirements
those manifests resolve to, runs an import probe for each installed component,
and writes an installation fingerprint.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_,
  unless every component of the target also declares another host (for example
  ``darwin-arm64`` for development). The target resolves only on a host its
  components support.
- One of the supported Python minors: 3.12, 3.11, or 3.10. Components declare
  the ranges they accept; the target resolves to the newest supported minor
  that satisfies every component in its closure, and ``rpent-install`` asks uv
  to fetch it when the host does not have it.
- A GPU and driver compatible with the target's PyTorch build for simulator
  and robot targets.

List targets
------------

.. code-block:: bash

   rpent-install list

The command prints every component with its name and kind, then every target
with the Python minor it resolves to and the components it installs.

A component is named ``<kind>-<directory>``: ``robot``, ``sim``, ``model``,
``tool``, or ``infra``. Every non-robot component is installable under its own
name; for example ``rpent-install install model-sam3`` installs the SAM 3.0
service and its dependencies, and ``rpent-install install sim-libero`` installs
the LIBERO simulator without a robot adapter. Robots install only through a
target, which names the environment the robot runs in.

Targets declared in ``installs/targets/`` or ``tests/targets/`` add the
compositions a single component cannot express: several components in one
environment or extra runtime dependencies. The two directories are discovered
as one namespace, and an explicit target may not reuse a component name; the
one exception is a robot's same-name override target, which must install that
robot. Test and development targets (``dev``, ``unit-cpu``) live in
``tests/targets/``.

Compound targets install one robot with the simulator and models it runs, for
example ``robot-libero`` (LIBERO with Pi0.5, SAM 3.0, and LeRobot export) and
``robot-yam`` (YAM with Pi0.5). Targets do not reference each other, so a
combination the repository does not name is installed as separate component
environments and connected at run time with endpoints.

``python`` in a component is either a version (``"3.11"``) or a range
(``">=3.10,<3.13"``). ``platforms`` lists the hosts a component supports and
defaults to ``["linux-x86_64"]``. ``install`` resolves both from the manifests,
and ``doctor`` reports when the manifests now resolve to different inputs than
the fingerprint recorded.

Install a target
----------------

From a checkout, install a target and activate its environment:

.. code-block:: bash

   rpent-install install robot-libero
   source .venvs/robot-libero/bin/activate

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

   ./rpent-install.sh install robot-libero
   source .venvs/robot-libero/bin/activate

The launcher runs the installer from a throwaway ``uv`` environment that adds
only ``packaging``; it needs ``uv`` on ``PATH`` and nothing else.

``rpent-install`` runs from a checkout. The wheel published to PyPI contains
only the core ``rpent`` package; ``robots/``, ``components/`` with their
``component.toml`` manifests, and ``installs/targets/`` ship only with the
source checkout and sdist. A non-editable ``pip install rpent`` provides the
CLI; run a specific robot or model service from a source checkout, where
``rpent-install`` can find the targets.

``install`` resolves the target from its manifests, so it reads no lock:
changing a manifest changes what the next install creates. The checked-in locks
under ``tests/locks/<target>.lock`` are optional reproduction artifacts for
rebuilding an environment with exactly the versions a maintainer verified; they
are not installation inputs, and ``install`` and ``check`` work without them.
``python -m tests.tooling.lock <target>`` regenerates one.

A target with ``core = false``, such as ``model-molmo``, skips the editable
RPent install and contains only that service's dependencies; start it with the
checkout on ``PYTHONPATH`` as shown in :doc:`../guides/flash`. A service that
serves other environments is installed as its own target on the serving host
(``model-openpi`` or ``model-sam3``); callers pass its endpoint at run time.
Re-running ``install`` reuses the environment and repairs a stale installation.

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
   name = "my-combo"

   [components.robot-franka]

   [components.model-sam3]

.. code-block:: bash

   ./rpent-install.sh install my-combo

Each ``[components.<name>]`` table must be empty: it selects a component, and
the component's manifest owns its dependencies and Python range. Resolution
checks the whole closure against the indexes the components declare, so
``env_conflicts``, disagreeing indexes, incompatible Python ranges, and hosts a
component does not support fail before the environment exists;
``install --dry-run`` prints the requirements without installing them.

Targets
-------

.. list-table::
   :header-rows: 1
   :widths: 34 8 58

   * - Target
     - Python
     - Contents
   * - ``minimal``
     - 3.12
     - Core RPent only; verifies the CLI and robot discovery without extra
       components.
   * - ``dev``
     - 3.12
     - Test dependencies for local development and CI.
   * - ``unit-cpu``
     - 3.11
     - CPU-only unit tests: core, test tools, the CPU Torch build, and the
       CPU flywheel stack.
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
   * - ``tool-flywheel``
     - 3.11
     - LeRobot trajectory export and replay.
   * - ``infra-rlinf``
     - 3.12
     - The RLinf release runtime shared by simulator and robot targets.
   * - ``robot-libero``
     - 3.11
     - LIBERO with Pi0.5, SAM 3.0, and LeRobot trajectory export and replay.
   * - ``robot-franka``
     - 3.12
     - Single-arm Franka with Pi0.5.
   * - ``robot-dual_franka``
     - 3.12
     - Dual-arm Franka with Pi0.5 and SAM 3.0.
   * - ``robot-yam``
     - 3.11
     - Dual-arm YAM with Pi0.5.
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

Every other component installs under its own name, for example
``model-molmo``, ``model-openpi``, ``model-sam3``, and ``model-rldx``;
``rpent-install list`` prints the full set. The Python column shows the minor
the manifests currently resolve to, which can be narrower than the range a
manifest accepts.

Install commands
----------------

Each target installs with its default environment under ``.venvs/<target>``.
On a fresh checkout, prefix the command as shown above.

.. code-block:: bash

   rpent-install install minimal
   rpent-install install dev
   rpent-install install unit-cpu
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
environment it inspected. ``--target`` overrides the target recorded in the
fingerprint and reports the mismatch as a warning. ``doctor`` compares the
stored fingerprint with every installation input (the manifests, the component
override files, and the repository's ``[tool.uv]`` settings), checks Python and
platform, runs ``uv pip check`` and the component probes, and prints the
fingerprint path and its SHA-256. ``doctor`` also probes a service installed in
another environment when ``--endpoint <name>=host:port`` or
``RPENT_<NAME>_ENDPOINT`` names its endpoint, and reports an endpoint it cannot
reach. ``uv`` resolves from the
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

``rpent-install check`` resolves targets from their manifests without installing
anything:

.. code-block:: bash

   rpent-install check --all
   rpent-install check minimal --inputs-hash
   rpent-install check robot-robotwin --resolve --platform linux-x86_64

It computes each target's ``requires`` closure and reports duplicate pins,
unsupported Python versions, platform mismatches, and repository data that
disagrees with the manifests. It downloads nothing and needs no lock.
``--inputs-hash`` prints the hash of one target's installation inputs and the
Python minor they resolve to; CI uses it as the environment cache key.
``--resolve`` additionally compiles every target with ``uv pip compile`` to
prove the declared dependencies have a solution; it uses the same code path as
``lock`` and reads package metadata from the configured indexes. ``--platform``
selects the host to resolve for and defaults to ``linux-x86_64``.

The remaining maintainer tools under ``tests/tooling/`` are not installed with
the wheel. Run them from a checkout through ``tests/tooling/rpent-tool.sh``,
which passes the module and its arguments to a throwaway ``uv`` environment:

.. code-block:: bash

   tests/tooling/rpent-tool.sh rpent.cli.install check --all
   tests/tooling/rpent-tool.sh tests.tooling.lock sim-robotwin
   tests/tooling/rpent-tool.sh tests.tooling.lock --all --check

``lock`` compiles a target's reproduction lock with ``uv pip compile`` and
records the upstream cutoff as an ``# exclude_newer`` header. Locks live under
``tests/locks/<target>.lock`` and change nothing about what ``install`` does.
``--check`` recompiles at that recorded instant and fails when the result
differs from the committed lock, so it reports changed manifests or a different
resolver rather than packages released since. ``lock --all`` reports a target that cannot resolve
on the current host and continues with the rest; the ``sim-robotwin`` lock
needs a Linux host with ``CUDA_HOME`` set because cuRobo builds metadata during
resolution. Linux locks target the ``manylinux_2_31`` baseline by default
(glibc 2.31, Ubuntu 20.04 or newer), because current GPU wheels are not
published for older baselines. The closure uses the newest baseline any of its
components declares; for example ``sim-robodojo`` declares
``manylinux = "2_35"`` for Isaac Sim 5.1 wheels. Regenerate locks with the
``uv`` release that generated them (0.13.7): an older release can resolve
different versions for the same inputs. The release job pins that version;
bump both together in a relock change.

The other maintainer tools cover repository structure and CI selection:
``python -m tests.tooling.layout`` checks component boundaries, and
``python -m tests.tooling.matrix`` and ``python -m tests.tooling.affected``
select and partition test environments. CI runs them with the same ``uv run``
bootstrap shown above.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
