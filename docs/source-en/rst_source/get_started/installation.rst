Installation
============

RPent installs a named environment profile, not a list of extras. Each profile
in ``envs/`` selects components and their placement; each component declares
its own dependencies in ``component.toml``. ``rpent-env`` creates the virtual
environment, installs exactly that recipe, runs an import probe for every
component it installs locally, and writes an installation fingerprint.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
- The Python minor version named by the profile. ``rpent-env`` asks uv to fetch
  it when the host does not have it.
- A GPU and driver compatible with the profile's PyTorch build for simulator
  and robot profiles.

List and check profiles
-----------------------

.. code-block:: bash

   rpent-env list
   rpent-env check --all

``check`` reads manifests and profiles, computes the ``requires`` closure, and
reports conflicting placements, duplicate pins, unsupported Python versions,
platform mismatches, and declared locks that no longer cover the requirements.
It downloads nothing.

Install a profile
------------------

From a checkout, install the profile into its own virtual environment:

.. code-block:: bash

   rpent-env install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

On a fresh checkout the ``rpent-env`` console script does not exist yet.
Bootstrap it without installing RPent first:

.. code-block:: bash

   uv run --no-project --python 3.11 --with packaging -- \
     python -m rpent.cli.env install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

Each profile gets its own virtual environment. Profiles pin different
simulator, robot, and model runtimes, so an environment already installed for
another profile is refused; install it under a different ``--venv``.

Re-running the command reuses the environment and repairs a stale install. The
installer uses the profile's lock when one exists and first checks that the
lock still covers every direct requirement; a stale lock fails with the
``rpent-env lock <profile>`` command that regenerates it. ``--dev`` appends the
test packages, which the lock does not cover, and resolves the generated
requirements instead. ``--dry-run`` prints the generated requirements. When a
profile places a component in an external environment, the installer prints
the command that installs that environment; run it against the same checkout.

Profiles
--------

.. list-table::
   :header-rows: 1
   :widths: 28 10 62

   * - Profile
     - Python
     - Contents
   * - ``minimal``
     - 3.11
     - Core RPent only; used to verify CLI and robot discovery without extras.
   * - ``dev``
     - 3.11
     - Test and lint dependencies; add it to another profile with
       ``rpent-env install <profile> --dev``.
   * - ``libero-sim`` / ``libero-pro`` / ``libero-plus``
     - 3.11
     - LIBERO variant with RLinf, Pi0.5, and SAM 3.0.
   * - ``libero-pro-flywheel``
     - 3.11
     - LIBERO-PRO with LeRobot trajectory export.
   * - ``libero-pro-molmo``
     - 3.11
     - LIBERO-PRO with Molmo grounding in the external ``molmo-server`` environment.
   * - ``libero-openpi-external``
     - 3.11
     - LIBERO-PRO that attaches to Pi0.5 in the external ``openpi-server`` environment
       with ``--am-endpoint``.
   * - ``franka-real`` / ``dual-franka-real``
     - 3.11
     - Real Franka hardware; dual-arm adds SAM 3.0.
   * - ``robocasa-sim``
     - 3.10
     - RoboCasa365 with RLinf's RoboCasa and RLDX stack.
   * - ``robotwin-sim``
     - 3.11
     - RoboTwin with LingBot-VLA and cuRobo.
   * - ``robodojo-sim``
     - 3.11
     - RoboDojo with its RLinf fork and Isaac Sim runtime.
   * - ``yam-real``
     - 3.11
     - YAM control and inference dependencies.
   * - ``molmo-server``
     - 3.11
     - Standalone Molmo server environment (``core = false``).
   * - ``geometry-eval``
     - 3.11
     - Geometry toolkit with its frozen CPU evaluation corpus.
   * - ``sam3-server`` / ``openpi-server``
     - 3.11
     - Single-capability diagnostic environments.

Install commands
----------------

Each profile has one install command below. On a fresh checkout, prefix the
command with ``uv run --no-project --python 3.11 --with packaging -- python -m
rpent.cli.env`` as shown above.

.. code-block:: bash

   rpent-env install minimal --venv .venv-minimal
   rpent-env install dev --venv .venv-dev
   rpent-env install libero-sim --venv .venv-libero-sim
   rpent-env install libero-pro --venv .venv-libero-pro
   rpent-env install libero-plus --venv .venv-libero-plus
   rpent-env install libero-pro-flywheel --venv .venv-libero-pro-flywheel
   rpent-env install libero-pro-molmo --venv .venv-libero-pro-molmo
   rpent-env install libero-openpi-external --venv .venv-libero-openpi-external
   rpent-env install franka-real --venv .venv-franka-real
   rpent-env install dual-franka-real --venv .venv-dual-franka-real
   rpent-env install robocasa-sim --venv .venv-robocasa-sim
   rpent-env install robotwin-sim --venv .venv-robotwin-sim
   rpent-env install robodojo-sim --venv .venv-robodojo-sim
   rpent-env install yam-real --venv .venv-yam-real
   rpent-env install molmo-server --venv .venv-molmo-server
   rpent-env install geometry-eval --venv .venv-geometry-eval
   rpent-env install sam3-server --venv .venv-sam3-server
   rpent-env install openpi-server --venv .venv-openpi-server

Diagnose and reproduce
----------------------

.. code-block:: bash

   rpent-env doctor --venv .venv-libero-pro
   rpent-env inspect --venv .venv-libero-pro
   rpent-env lock --all
   rpent-env lock --all --check

``doctor`` compares the stored fingerprint with the profile manifests, checks
Python and platform, runs ``uv pip check`` and the component probes, and can
probe external endpoints with ``--endpoint molmo=host:port``. ``inspect``
prints the fingerprint and its hash. ``lock`` compiles ``envs/locks/<profile>.lock``
with ``uv pip compile``; ``--check`` fails when a lock is stale. Linux locks
target the ``manylinux_2_31`` baseline by default (glibc 2.31, Ubuntu 20.04 or
newer), because current GPU wheels are not published for older baselines. A
profile whose components need a newer baseline sets ``manylinux``; for example
RoboDojo uses ``manylinux = "2_35"`` for Isaac Sim 5.1 wheels. ``lock --all``
reports a profile that cannot resolve on the current host and continues with
the rest; the ``robotwin-sim`` lock needs a Linux host with ``CUDA_HOME`` set
because cuRobo builds metadata during resolution. Regenerate locks with a
current ``uv``: an older release can resolve different versions for the same
inputs, so its output disagrees with the committed lock.

Run artifacts record the active profile, fingerprint hash, source commit, and
component names in ``run.json``.

Compatibility extras
--------------------

``scripts/gen_extras.py`` generates ``[project.optional-dependencies]`` and
``[tool.uv].conflicts`` in ``pyproject.toml`` from the same manifests and
profiles. They keep ``pip install -e ".[libero-pro]"`` working for one release;
do not edit that block by hand. ``scripts/gen_extras.py --check`` fails when the
block is stale. Profiles are the supported interface; use extras only for
migration.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
