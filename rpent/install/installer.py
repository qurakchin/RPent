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

"""Create a component environment, install it, and record its fingerprint."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet

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
    REQUIREMENTS_SCHEMA,
    read_core_dependencies,
    render_requirements,
    requirements_sha256,
)
from rpent.install.resolve import Resolution, python_errors, resolve
from rpent.utils.config import get_repo_root

#: Per-checkout state: generated requirements and virtualenvs.
STATE_DIR = ".rpent"


def environment_id(targets: Iterable[str]) -> str:
    """Return the file-name-safe identifier of a target set."""
    return "+".join(sorted(set(targets)))


def default_venv(root: Path, targets: Iterable[str]) -> Path:
    """Return the default virtualenv path for a target set."""
    return root / STATE_DIR / "venvs" / environment_id(targets)


def requirements_file(root: Path, targets: Iterable[str]) -> Path:
    """Return the generated requirements path for a target set."""
    return root / STATE_DIR / "requirements" / f"{environment_id(targets)}.txt"


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


def _supports_python(component: Component, version: str) -> bool:
    if component.python is None:
        return True
    try:
        supported = SpecifierSet(component.python)
    except InvalidSpecifier:
        # ``python_errors`` reports the invalid range with its manifest.
        return True
    return supported.contains(version, prereleases=True)


def _minor_candidates(components: Iterable[Component]) -> list[str]:
    """Return the minor versions named by the components' Python ranges."""
    candidates: set[tuple[int, int]] = set()
    for component in components:
        if component.python is None:
            continue
        try:
            supported = SpecifierSet(component.python)
        except InvalidSpecifier:
            continue
        for specifier in supported:
            match = re.fullmatch(r"(\d+)\.(\d+)", specifier.version)
            if match is None:
                continue
            major, minor = int(match.group(1)), int(match.group(2))
            candidates.add((major, minor))
            candidates.add((major, max(minor - 1, 0)))
    return [f"{major}.{minor}" for major, minor in sorted(candidates, reverse=True)]


def choose_python(components: Iterable[Component]) -> str:
    """Return the interpreter to create a new environment with.

    The running interpreter is the first choice: the caller already has it, and
    an environment built with it needs no download. When a component rules it
    out, the highest version every component supports is used instead; a target
    set with no common version is reported by ``python_errors`` before the
    environment is created.
    """
    components = list(components)
    host = f"{sys.version_info.major}.{sys.version_info.minor}"
    for version in (host, *_minor_candidates(components)):
        if all(_supports_python(component, version) for component in components):
            return version
    return host


def resolve_targets(
    targets: Iterable[str],
    catalog: Catalog,
    *,
    root: Path,
    platform: str | None = None,
) -> Resolution:
    """Resolve component names against the checkout's manifests."""
    core = read_core_dependencies(root)
    return resolve(
        targets,
        catalog,
        core_dependencies=core,
        platform=platform,
    )


def _check_existing(destination: Path, targets: Sequence[str]) -> None:
    """Reject a virtualenv that was installed for a different component set."""
    existing = read_fingerprint(destination)
    if existing is None:
        return
    recorded = existing.get("targets")
    if recorded is None:
        return
    if sorted(recorded) != sorted(targets):
        raise InstallError(
            f"{destination} is already installed for {', '.join(recorded)}; "
            "environments cannot share a virtualenv because their dependencies "
            f"differ. Install this set into its own environment with "
            f"`--venv {destination.parent / environment_id(targets)}`, or "
            f"replace the existing one by removing {destination}"
        )


def install(
    targets: Iterable[str],
    *,
    root: Path | None = None,
    venv: Path | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """Install ``targets`` and their closure into one environment.

    Returns the written fingerprint.
    """
    repo_root = (root or get_repo_root()).resolve()
    catalog = discover(repo_root)
    resolution = resolve_targets(
        targets, catalog, root=repo_root, platform=runtime_platform()
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    core = read_core_dependencies(repo_root)
    requirements = render_requirements(resolution, core_dependencies=core)
    destination = (venv or default_venv(repo_root, resolution.targets)).resolve()
    requirements_path = requirements_file(repo_root, resolution.targets)

    if dry_run:
        print(requirements, end="")
        return {
            "targets": list(resolution.targets),
            "venv": str(destination),
            "requirements": requirements,
        }

    _check_existing(destination, resolution.targets)

    if venv_python(destination).exists():
        interpreter = _python_version(venv_python(destination))
    else:
        interpreter = choose_python(resolution.components.values())
    unsupported = python_errors(
        interpreter, resolution.components.values(), owner=str(destination)
    )
    if unsupported:
        raise InstallError(
            "\n".join(unsupported)
            + f"\nno interpreter supports every component; remove {destination} "
            "and rerun with a matching `uv venv --python <version>`"
        )

    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(requirements, encoding="utf-8")

    uv = find_uv()
    python = venv_python(destination)
    if not python.exists():
        if verbose:
            print(f"$ {uv} venv --python {interpreter} {destination}")
        run_command(
            [uv, "venv", "--python", interpreter, str(destination)],
            cwd=repo_root,
        )
        python = venv_python(destination)
    if not python.exists():
        raise InstallError(
            f"{destination} exists but has no Python interpreter; remove it and "
            f"rerun `{repair_command(resolution)}`"
        )

    install_command = [uv, "pip", "install", "--python", str(python)]
    install_command.extend(index_options(resolution))
    for component in resolution.components.values():
        for override in component.overrides:
            install_command.extend(["--override", str(override)])
    install_command.extend(["-r", str(requirements_path)])
    if verbose:
        print(f"$ {' '.join(install_command)}")
    # uv discovers ``[tool.uv]`` by walking up from its working directory, so
    # run it in the checkout: the recorded inputs live there, and an environment
    # installed from another directory must not resolve with other settings.
    run_command(install_command, cwd=repo_root)

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

    _probe_components(resolution, python, repo_root, verbose=verbose)
    run_command([uv, "pip", "check", "--python", str(python)], cwd=repo_root)

    frozen = run_command(
        [uv, "pip", "freeze", "--python", str(python)], capture=True, cwd=repo_root
    )
    commit, dirty = source_state(repo_root)
    fingerprint = {
        "schema": REQUIREMENTS_SCHEMA,
        "targets": list(resolution.targets),
        "python": _python_version(python),
        "platform": runtime_platform(),
        "source_commit": commit,
        "source_dirty": dirty,
        "components": {
            name: {"manifest_sha256": component.manifest_sha256}
            for name, component in resolution.components.items()
        },
        "requirements_sha256": requirements_sha256(
            resolution,
            root=repo_root,
            core_dependencies=core,
        ),
        "freeze_sha256": freeze_sha256(frozen),
        "requirements_file": str(requirements_path.relative_to(repo_root)),
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
    """Return the uv index options the environment resolves with."""
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


def repair_command(resolution: Resolution) -> str:
    """Return the command that rebuilds the same installation."""
    return f"rpent-install install {' '.join(resolution.targets)}"


def _probe_components(
    resolution: Resolution,
    python: Path,
    root: Path,
    *,
    verbose: bool,
) -> None:
    environment = {**os.environ, "PYTHONPATH": str(root)}
    for name, component in resolution.components.items():
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
                f"  install: {repair_command(resolution)} "
                f"--venv {python.parent.parent}\n"
                f"{exc}"
            ) from exc
