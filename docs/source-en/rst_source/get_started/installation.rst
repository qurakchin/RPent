Installation
============

RPent installs a named environment profile. Each profile
in ``installs/profiles/`` selects components and their placement; each component declares
its own dependencies in ``component.toml``. ``rpent-install`` creates the virtual
environment, installs exactly that recipe, runs an import probe for every
component it installs locally, and writes an installation fingerprint.

Requirements
------------

- Linux ``x86_64`` and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
- The Python minor version named by the profile. ``rpent-install`` asks uv to fetch
  it when the host does not have it.
- A GPU and driver compatible with the profile's PyTorch build for simulator
  and robot profiles.

List and check profiles
-----------------------

.. code-block:: bash

   rpent-install list
   rpent-install check --all

``check`` reads manifests and profiles, computes the ``requires`` closure, and
reports conflicting placements, duplicate pins, unsupported Python versions,
and platform mismatches. It downloads nothing. ``--resolve`` additionally
uses ``uv pip compile`` to check that the declared dependencies have a solution.
It reads package metadata from the configured indexes and discards the temporary
compiled requirements after the check.

Install a profile
------------------

From a checkout, install the profile into its own virtual environment:

.. code-block:: bash

   rpent-install install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

On a fresh checkout the ``rpent-install`` console script does not exist yet.
``scripts/rpent-install.sh`` bootstraps it without installing RPent first:

.. code-block:: bash

   ./scripts/rpent-install.sh install libero-pro --venv .venv-libero-pro
   source .venv-libero-pro/bin/activate

``rpent-install`` runs from a checkout. The wheel published to PyPI contains
only the core ``rpent`` package; ``robots/``, ``components/`` with their
``component.toml`` manifests, and ``installs/profiles/`` ship only with the
source checkout and sdist. A non-editable ``pip install rpent`` provides the
CLI; run a specific robot or model service from a source checkout,
where ``rpent-install`` can find the profiles.

Each profile gets its own virtual environment. Profiles pin different
simulator, robot, and model runtimes, so an environment already installed for
another profile is refused; install it under a different ``--venv``. Without
``--venv``, a profile installs into ``.rpent/venvs/<profile>`` under the
checkout; ``.rpent/`` is local state and is ignored by git, so later
``install`` and ``doctor`` runs find the same environment. A profile with
``core = false`` (for example ``molmo-server``) skips the editable RPent
install and contains only that service's dependencies; start it with the
checkout on ``PYTHONPATH`` as shown in :doc:`../guides/flash`.

Re-running the command reuses the environment and repairs a stale install.
The installer generates requirements from the profile and component manifests,
then lets ``uv pip install`` resolve them. Direct version constraints and Git
revisions remain in the manifests; transitive versions may differ between fresh
installs as upstream packages change. ``--dev`` adds the test dependencies to
the generated requirements. ``--dry-run`` prints those requirements. When a
profile places a component in an external environment, the installer prints
the command that installs that environment; run it against the same checkout.

The Franka, Dual Franka, YAM, RoboCasa, RoboDojo, and RoboTwin robots declare
component manifests, but no profile selects them yet. Their compatibility
extras remain the documented install path — for example
``uv pip install -e ".[franka]"`` in their own guides; see
:doc:`../real_world_robots/franka`, :doc:`../real_world_robots/yam`, and the
simulator guides. Installing one as a development environment with
``rpent-install install <robot>`` also works, but it composes only that
component and is not a supported runtime setup.

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
     - Core RPent only; used to verify CLI and robot discovery without robot dependencies.
   * - ``dev``
     - 3.11
     - Test and lint dependencies; add it to another profile with
       ``rpent-install install <profile> --dev``.
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
   * - ``molmo-server``
     - 3.11
     - Standalone Molmo server environment (``core = false``).
   * - ``sam3-server`` / ``openpi-server``
     - 3.11
     - Single-capability diagnostic environments.
   * - ``unit-cpu``
     - 3.11
     - CPU-only unit-test dependencies; installed once per supported Python
       minor in CI.

Install commands
----------------

Each profile has one install command below. On a fresh checkout, run it
through ``./scripts/rpent-install.sh`` instead of ``rpent-install``, as shown
above.

.. code-block:: bash

   rpent-install install minimal --venv .venv-minimal
   rpent-install install dev --venv .venv-dev
   rpent-install install libero-sim --venv .venv-libero-sim
   rpent-install install libero-pro --venv .venv-libero-pro
   rpent-install install libero-plus --venv .venv-libero-plus
   rpent-install install libero-pro-flywheel --venv .venv-libero-pro-flywheel
   rpent-install install libero-pro-molmo --venv .venv-libero-pro-molmo
   rpent-install install libero-openpi-external --venv .venv-libero-openpi-external
   rpent-install install molmo-server --venv .venv-molmo-server
   rpent-install install sam3-server --venv .venv-sam3-server
   rpent-install install openpi-server --venv .venv-openpi-server
   rpent-install install unit-cpu --venv .venv-unit-cpu

Diagnose an environment
-----------------------

.. code-block:: bash

   rpent-install doctor --venv .venv-libero-pro
   rpent-install inspect --venv .venv-libero-pro

``doctor`` compares the stored fingerprint with every recorded installation
input (the manifests, the component override files,
and the repository's ``[tool.uv]`` settings), checks Python and platform, runs
``uv pip check`` and the component probes, and can
probe external endpoints with ``--endpoint molmo=host:port``. ``uv`` resolves
from the checkout, so the compared settings do not depend on the directory
the command is invoked from; user-level ``uv`` configuration
(``~/.config/uv``) is outside the comparison. The fingerprint also records the
input mode it was written with, so a venv installed by an older ``rpent-install``
is reported as needing a reinstall rather than as drifted. A single
component can be installed for development with
``rpent-install install <component>``; its fingerprint records
``install_kind = "component"`` and the interpreter
it used, and ``doctor`` rebuilds that diagnostic profile with the recorded
interpreter rather than the one running the check. ``inspect`` prints the
fingerprint and its hash. ``doctor`` also compares the installed package set
with its recorded freeze hash. These checks detect environment changes; they
do not pin future dependency resolution. The publish workflow calls Full CI
with ``full: true`` to install and diagnose every profile before publishing.

For ``check --resolve``, Linux profiles target ``manylinux_2_31`` by default
(glibc 2.31, Ubuntu 20.04 or newer). A profile can raise that baseline with
``manylinux``.
Checking a configuration that builds cuRobo with ``--resolve`` needs a Linux
host with ``CUDA_HOME`` set because cuRobo builds metadata during resolution. A failed
resolution is reported without stopping checks of the remaining profiles.

Run artifacts record the active profile, fingerprint hash, source commit, and
component names in ``run.json``.

See each simulator or robot page for platform preparation, checkpoints, and
assets.
