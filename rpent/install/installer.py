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

"""Create a target environment, install it, and record its fingerprint."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import (
    freeze_sha256,
    read_fingerprint,
    runtime_platform,
    source_state,
    write_fingerprint,
)
from rpent.install.manifest import compose_target
from rpent.install.requirements import (
    INPUT_SCHEMA,
    read_core_dependencies,
    render_requirements,
    requirements_sha256,
)
from rpent.install.resolve import Resolution, resolve
from rpent.utils.config import get_repo_root

#: Default per-target virtualenvs; gitignored installation output.
VENV_DIR = ".venvs"
#: Rendered requirements file kept inside the installed virtualenv.
REQUIREMENTS_NAME = "rpent-requirements.txt"


def default_venv(root: Path, target_name: str) -> Path:
    """Return the default virtualenv path for the environment ``target_name``."""
    return root / VENV_DIR / target_name


def environment_name(target_name: str, extra_components: tuple[str, ...] = ()) -> str:
    """Return the environment name a target and its ``--with`` components form.

    A plain target keeps the environment named after it. Adding components
    gives the composition its own environment, so an unmodified install and a
    test-tool install never reuse each other's packages.
    """
    if not extra_components:
        return target_name
    return "+".join((target_name, *extra_components))


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
        )
    except FileNotFoundError as exc:
        raise InstallError(f"command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"command failed ({exc.returncode}): {' '.join(command)}"
        if detail:
            message += f"\n{detail}"
        raise InstallError(message) from exc
    return result.stdout if capture else ""


def target_resolution(
    target: str,
    catalog: Catalog,
    *,
    root: Path,
    platform: str | None = None,
    extra_components: tuple[str, ...] = (),
) -> Resolution:
    """Resolve one named target for ``platform``, defaulting to this host.

    ``extra_components`` extends the target's selection for one environment,
    the same way ``install --with`` does.
    """
    found = catalog.targets.get(target)
    if found is None:
        known = ", ".join(sorted(catalog.targets))
        raise InstallError(f"unknown target {target!r}; known targets: {known}")
    unknown = [name for name in extra_components if name not in catalog.components]
    if unknown:
        known = ", ".join(sorted(catalog.components))
        raise InstallError(
            f"unknown component(s) for --with: {', '.join(unknown)}; "
            f"known components: {known}"
        )
    composed = compose_target(found, extra_components)
    core = read_core_dependencies(root) if composed.core else ()
    return resolve(
        composed,
        catalog,
        core_dependencies=core,
        platform=platform or runtime_platform(),
    )


def install(
    target_name: str,
    *,
    root: Path | None = None,
    venv: Path | None = None,
    force: bool = False,
    verbose: bool = True,
    dry_run: bool = False,
    platform: str | None = None,
    extra_components: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Install one named target and return the written fingerprint.

    ``extra_components`` composes additional components, such as the test tools
    of ``infra-dev``, into the same environment. ``dry_run`` stops after
    resolving and validating the composition, printing the requirements it
    would install. Nothing is written and no virtualenv is created, so the
    resolved set is reviewable before it costs a download.
    """
    repo_root = (root or get_repo_root()).resolve()
    catalog = discover(repo_root)
    resolution = target_resolution(
        target_name,
        catalog,
        root=repo_root,
        platform=platform,
        extra_components=extra_components,
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    target = resolution.target
    core = read_core_dependencies(repo_root) if target.core else ()
    main_requirements = render_requirements(
        resolution, root=repo_root, core_dependencies=core
    )
    env_name = environment_name(target.name, extra_components)
    destination = (venv or default_venv(repo_root, env_name)).resolve()

    python_version = resolution.python

    if dry_run:
        composed = f" with {', '.join(extra_components)}" if extra_components else ""
        print(
            f"# target {target.name}{composed}: python {python_version} "
            f"on {resolution.platform}"
        )
        print(main_requirements, end="")
        return {}

    existing = read_fingerprint(destination)
    if existing is not None:
        existing_name = existing.get("target")
        if existing_name != target.name:
            raise InstallError(
                f"{destination} is already installed for target "
                f"{existing_name!r}; environments cannot share a virtualenv "
                f"because their dependencies differ. Install "
                f"{target.name!r} into its own environment, for example "
                f"`--venv {default_venv(repo_root, env_name)}`"
            )
    elif destination.exists() and any(destination.iterdir()) and not force:
        raise InstallError(
            f"{destination} is not empty and records no installation "
            "fingerprint; pass --force to install into it anyway"
        )

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
            f"rerun `{install_invocation(target.name, extra_components=extra_components)}`"
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
    # run it in the checkout: the recorded inputs live there, and a target
    # installed from another directory must not resolve with other settings.
    run_command(install_command, cwd=repo_root)

    if target.core:
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

    _probe_components(
        resolution,
        python,
        repo_root,
        verbose=verbose,
        extra_components=extra_components,
    )
    run_command([uv, "pip", "check", "--python", str(python)], cwd=repo_root)

    frozen = run_command(
        [uv, "pip", "freeze", "--python", str(python)], capture=True, cwd=repo_root
    )
    commit, dirty = source_state(repo_root)
    fingerprint = {
        "schema": INPUT_SCHEMA,
        "target": target.name,
        "with": list(extra_components),
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


def probe_source(probe: str) -> str:
    """Return the source an install probe runs for ``probe``.

    Importing the package alone is a weak check: slice entries stay lazy so a
    missing optional dependency does not break discovery. Probe the slice's
    role module too, preferring the a_5 name ``adapter`` and falling back to
    the current ``robot_spec`` until S2 renames it, so the probe verifies real
    dependencies without pinning the manifest to a file name.
    """
    candidates = "".join(
        f'    "{probe}.{name}",\n' for name in ("adapter", "robot_spec")
    )
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


def install_invocation(
    target_name: str,
    *,
    venv: Path | None = None,
    extra_components: tuple[str, ...] = (),
) -> str:
    """Return the command that reproduces an installation."""
    command = f"rpent-install install {target_name}"
    for name in extra_components:
        command += f" --with {name}"
    if venv is not None:
        command += f" --venv {venv}"
    return command


def repair_command(
    resolution: Resolution, extra_components: tuple[str, ...] = ()
) -> str:
    """Return the command that rebuilds the same installation."""
    return install_invocation(resolution.target.name, extra_components=extra_components)


def _probe_components(
    resolution: Resolution,
    python: Path,
    root: Path,
    *,
    verbose: bool,
    extra_components: tuple[str, ...] = (),
) -> None:
    environment = {**os.environ, "PYTHONPATH": str(root)}
    for name, component in sorted(resolution.components.items()):
        probe = component.probe
        if verbose:
            print(f"probe {name}: import {probe}")
        try:
            run_command(
                [str(python), "-c", probe_source(probe)],
                env=environment,
                capture=True,
            )
        except InstallError as exc:
            raise InstallError(
                f"component {name!r} is not importable in {python.parent.parent}\n"
                f"  probe: import {probe}\n"
                f"  install: "
                f"{install_invocation(resolution.target.name, venv=python.parent.parent, extra_components=extra_components)}\n"
                f"{exc}"
            ) from exc
