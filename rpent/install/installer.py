# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create an environment from components, install it, and fingerprint it."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    freeze_sha256,
    read_fingerprint,
    runtime_platform,
    source_state,
    write_fingerprint,
)
from rpent.install.manifest import Component
from rpent.install.requirements import (
    INPUT_SCHEMA,
    read_core_dependencies,
    render_requirements,
    requirements_sha256,
)
from rpent.install.resolve import Resolution, resolve
from rpent.utils.config import get_repo_root

#: Default per-environment virtualenvs; gitignored installation output.
VENV_DIR = ".venvs"
#: Rendered requirements file kept inside the installed virtualenv.
REQUIREMENTS_NAME = "rpent-requirements.txt"
#: Upper bound for one import probe. A model runtime can take minutes to import
#: on a cold filesystem, but a hung probe must not block installation forever.
PROBE_TIMEOUT_SECONDS = 3600
#: Modules a probe imports after its package, by component kind. A slice's
#: ``__init__`` stays lazy so discovery works without optional dependencies;
#: importing the role module proves the dependencies it actually runs with.
#: Model manifests already probe their server module, so they need no entry.
ROLE_MODULES = {
    "robot": ("adapter", "robot_spec"),
    "sim": ("env_server",),
    "model": (),
    "tool": ("cli",),
    "infra": (),
}
#: Distributions ``uv venv`` itself may seed. A virtualenv holding only these
#: has nothing the user installed, so the installer may repair it in place.
_BASE_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})


def default_venv(root: Path, environment: str) -> Path:
    """Return the default virtualenv path for ``environment``."""
    return root / VENV_DIR / environment


def requirements_file(venv: Path) -> Path:
    """Return the requirements path recorded inside ``venv``.

    The file lives in the environment it produced, so an installed venv carries
    its own reproduction input and removing it needs no separate cleanup.
    """
    return Path(venv) / REQUIREMENTS_NAME


def venv_python(venv: Path) -> Path:
    """Return the interpreter path inside a virtualenv."""
    candidate = Path(venv) / "bin" / "python"
    if candidate.exists():
        return candidate
    return Path(venv) / "Scripts" / "python.exe"


def find_uv() -> str:
    """Return the uv executable or raise an actionable error."""
    override = os.environ.get("RPENT_UV")
    if override:
        return override
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError(
            "uv is required to install RPent environments: "
            "https://docs.astral.sh/uv/getting-started/installation/"
        )
    return uv


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    capture: bool = False,
    cwd: Path | None = None,
    timeout: float | None = None,
) -> str:
    """Run ``command`` and return its captured stdout.

    ``cwd`` is passed to every ``uv`` call that resolves or installs packages:
    uv discovers ``[tool.uv]`` from its working directory, so resolution must
    happen in the checkout rather than in the caller's directory.
    """
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=capture,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise InstallError(f"command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise InstallError(
            f"command timed out after {exc.timeout}s: {' '.join(command)}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"command failed ({exc.returncode}): {' '.join(command)}"
        if detail:
            message += f"\n{detail}"
        raise InstallError(message) from exc
    return result.stdout if capture else ""


def resolution_for(
    components: Iterable[str],
    catalog: Catalog,
    *,
    root: Path,
    platform: str | None = None,
) -> Resolution:
    """Resolve requested components into one environment for ``platform``.

    Repeated names collapse, so naming a component twice installs it once. An
    empty request is the core-only ``minimal`` environment.
    """
    requested = tuple(dict.fromkeys(components))
    unknown = [name for name in requested if name not in catalog.components]
    if unknown:
        known = ", ".join(sorted(catalog.components))
        raise InstallError(
            f"unknown component(s): {', '.join(unknown)}; known components: {known}"
        )
    return resolve(
        requested,
        catalog,
        core_dependencies=read_core_dependencies(root),
        platform=platform or runtime_platform(),
    )


def install(
    *components: str,
    root: Path | None = None,
    venv: Path | None = None,
    force: bool = False,
    verbose: bool = True,
    dry_run: bool = False,
    platform: str | None = None,
) -> dict[str, Any]:
    """Install one environment from ``components`` and return its fingerprint.

    The environment name is the sorted join of the requested components, or
    ``minimal`` when none are named. ``dry_run`` stops after resolving and
    validating the composition, printing the requirements it would install.
    Nothing is written and no virtualenv is created, so the resolved set is
    reviewable before it costs a download.
    """
    repo_root = (root or get_repo_root()).resolve()
    catalog = discover(repo_root)
    resolution = resolution_for(
        components,
        catalog,
        root=repo_root,
        platform=platform,
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    core = read_core_dependencies(repo_root)
    main_requirements = render_requirements(resolution, core_dependencies=core)
    env_name = resolution.name
    destination = (venv or default_venv(repo_root, env_name)).resolve()

    python_version = resolution.python

    if dry_run:
        print(
            f"# environment {env_name}: python {python_version} "
            f"on {resolution.platform}"
        )
        print(main_requirements, end="")
        return {}

    existing = read_fingerprint(destination)
    if existing is not None:
        recorded = existing.get("environment")
        if recorded != env_name:
            raise InstallError(
                f"{destination} is already installed for environment "
                f"{recorded!r}; environments cannot share a virtualenv "
                f"because their dependencies differ. Install {env_name!r} into "
                f"its own environment, for example "
                f"`--venv {default_venv(repo_root, env_name)}`"
            )
    elif destination.exists() and any(destination.iterdir()) and not force:
        state = _venv_state(destination)
        if state == "foreign":
            raise InstallError(
                f"{destination} is not empty and belongs to another tool; "
                "pass --force to install into it anyway"
            )
        if verbose and state == "rpent":
            print(f"repairing {destination}: it records no fingerprint")

    uv = find_uv()
    python = venv_python(destination)
    if not python.exists():
        if verbose:
            print(f"$ {uv} venv --python {python_version} {destination}")
        run_command(
            [uv, "venv", "--python", python_version, str(destination)],
            cwd=repo_root,
        )
        python = venv_python(destination)
    if not python.exists():
        raise InstallError(
            f"{destination} exists but has no Python interpreter; remove it and "
            f"rerun `{install_invocation(resolution.requested)}`"
        )

    requirements_path = requirements_file(destination)
    requirements_path.write_text(main_requirements, encoding="utf-8")

    # Install the requirements rendered from the manifests. A checked-in lock
    # is a reproduction artifact, not an installation input, so a stale or
    # missing lock never blocks installing or diagnosing an environment.
    install_command = [uv, "pip", "install", "--python", str(python)]
    install_command.extend(index_options(resolution))
    for component in resolution.components.values():
        for override in component.overrides:
            install_command.extend(["--override", str(override)])
    install_command.extend(["-r", str(requirements_path)])
    if verbose:
        print(f"$ {' '.join(install_command)}")
    # uv discovers ``[tool.uv]`` by walking up from its working directory, so
    # run it in the checkout: the recorded inputs live there, and an
    # environment installed from another directory must not resolve with other
    # settings.
    run_command(install_command, cwd=repo_root)

    # The checkout is always installed editable: an environment without it
    # cannot import the component manifests, and the probes below run isolated
    # from the caller's ``PYTHONPATH``.
    editable = [
        uv,
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        "-e",
        str(repo_root),
    ]
    if verbose:
        print(f"$ {' '.join(editable)}")
    run_command(editable, cwd=repo_root)

    _probe_components(resolution, python, verbose=verbose)
    run_command([uv, "pip", "check", "--python", str(python)], cwd=repo_root)

    frozen = run_command(
        [uv, "pip", "freeze", "--python", str(python)], capture=True, cwd=repo_root
    )
    commit, dirty = source_state(repo_root)
    fingerprint = {
        "schema": INPUT_SCHEMA,
        "environment": env_name,
        "requested": list(resolution.requested),
        "python": _python_version(python),
        "source_commit": commit,
        "source_dirty": dirty,
        "platform": resolution.platform,
        "components": {
            name: {"manifest_sha256": component.manifest_sha256}
            for name, component in sorted(resolution.components.items())
        },
        "requirements_sha256": requirements_sha256(
            resolution,
            root=repo_root,
            core_dependencies=core,
        ),
        "freeze_sha256": freeze_sha256(frozen),
        "requirements_file": REQUIREMENTS_NAME,
        "installed_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    written = write_fingerprint(destination, fingerprint)
    if verbose:
        print(f"installation fingerprint: {written}")
    return fingerprint


def index_options(resolution: Resolution) -> list[str]:
    """Return uv's index flags for a resolved environment."""
    options: list[str] = []
    if resolution.index_url:
        options.extend(["--index-url", resolution.index_url])
    for url in resolution.extra_index_urls:
        options.extend(["--extra-index-url", url])
    if resolution.index_strategy:
        options.extend(["--index-strategy", resolution.index_strategy])
    return options


def _python_version(python: Path) -> str:
    try:
        return run_command(
            [str(python), "-c", "import platform; print(platform.python_version())"],
            capture=True,
        ).strip()
    except InstallError:
        return "unknown"


def _venv_state(destination: Path) -> str:
    """Classify a non-empty virtualenv that records no fingerprint.

    ``rpent`` is an environment an earlier ``rpent-install`` wrote whose
    fingerprint was lost: its rendered requirements are still inside, so
    reinstalling repairs it in place. ``base`` holds no third-party
    distribution, so nothing a user installed can be lost. Anything else
    belongs to another tool and needs ``--force``.
    """
    if requirements_file(destination).is_file():
        return "rpent"
    distributions: set[str] = set()
    for pattern in ("lib/python*/site-packages", "Lib/site-packages"):
        for directory in destination.glob(pattern):
            distributions.update(
                entry.name
                for entry in directory.iterdir()
                if entry.name.endswith((".dist-info", ".egg-info"))
            )
    if not distributions:
        return "base"
    names = {entry.partition("-")[0] for entry in distributions}
    if names <= _BASE_DISTRIBUTIONS:
        return "base"
    return "foreign"


def probe_source(probe: str, kind: str) -> str:
    """Return the source an install probe runs for ``probe``.

    Importing the package alone is a weak check: slice entries stay lazy so a
    missing optional dependency does not break discovery. The probe also
    imports the component's role module when one exists, so a broken runtime
    dependency surfaces at install time rather than at first use.
    """
    role_modules = ROLE_MODULES[kind]
    if not role_modules:
        return f"import {probe}\n"
    candidates = "".join(f'    "{probe}.{name}",\n' for name in role_modules)
    return (
        "import importlib\n"
        "import importlib.util\n"
        f"import {probe}\n"
        "for name in (\n"
        f"{candidates}"
        "):\n"
        "    try:\n"
        "        found = importlib.util.find_spec(name)\n"
        "    except (ImportError, AttributeError, ValueError):\n"
        "        found = None\n"
        "    if found is not None:\n"
        "        importlib.import_module(name)\n"
        "        break\n"
    )


def probe_component(
    python: Path,
    component: Component,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> str | None:
    """Import one component's probe and return a failure detail, if any.

    The interpreter runs isolated: the checkout is installed editable, so the
    probe proves what the environment contains instead of what the caller's
    ``PYTHONPATH`` happens to expose.
    """
    try:
        run_command(
            [str(python), "-I", "-c", probe_source(component.probe, component.kind)],
            capture=True,
            timeout=timeout,
        )
    except InstallError as exc:
        return str(exc)
    return None


def install_invocation(
    requested: Iterable[str],
    *,
    venv: Path | None = None,
) -> str:
    """Return the command that reproduces an installation."""
    command = "rpent-install install"
    names = " ".join(requested)
    if names:
        command += f" {names}"
    if venv is not None:
        command += f" --venv {venv}"
    return command


def _probe_components(
    resolution: Resolution,
    python: Path,
    *,
    verbose: bool,
) -> None:
    for name, component in sorted(resolution.components.items()):
        if verbose:
            print(f"probe {name}: import {component.probe}")
        detail = probe_component(python, component)
        if detail is not None:
            raise InstallError(
                f"component {name!r} is not importable in {python.parent.parent}\n"
                f"  probe: import {component.probe}\n"
                f"  install: "
                f"{install_invocation(resolution.requested, venv=python.parent.parent)}\n"
                f"{detail}"
            )
