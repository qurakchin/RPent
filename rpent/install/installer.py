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

"""Create a profile environment, install it, and record its fingerprint."""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess
import sys
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
from rpent.install.lock_coverage import lock_problems
from rpent.install.manifest import Component, Profile, Selection
from rpent.install.requirements import (
    read_core_dependencies,
    render_requirements,
    requirements_sha256,
)
from rpent.install.resolve import Resolution, resolve
from rpent.utils.config import get_repo_root

#: Per-checkout state: generated requirements and per-profile virtualenvs.
STATE_DIR = ".rpent"


def default_venv(root: Path, profile: Profile) -> Path:
    """Return the default virtualenv path for ``profile``."""
    return root / STATE_DIR / "venvs" / profile.name


def requirements_file(root: Path, profile: Profile, environment: str) -> Path:
    """Return the generated requirements path for one environment."""
    if environment == profile.name:
        return root / STATE_DIR / "envs" / f"{profile.name}.txt"
    return root / STATE_DIR / "envs" / f"{profile.name}.{environment}.txt"


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
) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=capture,
            env=env,
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


def _with_dev(profile: Profile, catalog: Catalog) -> Profile:
    dev = catalog.profiles.get("dev")
    if dev is None:
        return profile
    components = dict(profile.components)
    for name, selection in dev.components.items():
        components.setdefault(name, selection)
    return dataclasses.replace(
        profile,
        components=components,
        dependencies=tuple(dict.fromkeys(profile.dependencies + dev.dependencies)),
        extra_index_urls=tuple(
            dict.fromkeys(profile.extra_index_urls + dev.extra_index_urls)
        ),
    )


def _supported_python(component: Component) -> str:
    """Return the running Python, or the nearest minor the component supports.

    A single-component install is a diagnostic run from the current
    interpreter. When the interpreter is outside the component's range, fall
    back to the highest supported minor so ``uv venv`` can create a usable
    environment instead of failing every component check.
    """
    host = f"{sys.version_info.major}.{sys.version_info.minor}"
    if component.python is None:
        return host
    try:
        supported = SpecifierSet(component.python)
    except InvalidSpecifier:
        return host
    if supported.contains(host, prereleases=True):
        return host
    candidates: set[tuple[int, int]] = set()
    for specifier in supported:
        match = re.fullmatch(r"(\d+)\.(\d+)", specifier.version)
        if match is None:
            continue
        major, minor = int(match.group(1)), int(match.group(2))
        candidates.add((major, minor))
        if minor:
            candidates.add((major, minor - 1))
    for major, minor in sorted(candidates, reverse=True):
        value = f"{major}.{minor}"
        if supported.contains(value, prereleases=True):
            return value
    return host


def _profiles_placing(catalog: Catalog, component_name: str) -> list[str]:
    """Return the profiles that list ``component_name``."""
    return sorted(
        name
        for name, profile in catalog.profiles.items()
        if component_name in profile.components
    )


def component_profile(
    component_name: str,
    catalog: Catalog,
    *,
    root: Path,
    python: str | None = None,
    variant: str | None = None,
) -> Profile:
    """Build a development-only profile for one component.

    The component is placed in the synthetic profile's own environment, so a
    component that only allows an external or remote placement cannot be
    installed this way; the error names the profiles that can install it.
    ``python`` pins the interpreter used for an installed diagnostic
    environment; ``doctor`` passes the version recorded in the fingerprint so
    the profile hashes the same no matter which interpreter runs the check.
    """
    component = catalog.components[component_name]
    if "in-env" not in component.placements:
        places = _profiles_placing(catalog, component_name)
        hint = (
            f"install one of the profiles that place it: {', '.join(places)}"
            if places
            else (
                f"no profile places it yet; add [components.{component_name}] to "
                "a profile that runs it"
            )
        )
        raise InstallError(
            f"component {component_name!r} allows {', '.join(component.placements)} "
            f"placement but no in-env placement; {hint}"
        )
    if component.variant_required and variant is None:
        choices = "|".join(sorted(component.optional))
        places = _profiles_placing(catalog, component_name)
        hint = (
            f" or install a profile that selects one: {', '.join(places)}"
            if places
            else ""
        )
        raise InstallError(
            f"component {component_name!r} requires a variant; pass "
            f"`--variant <{choices}>`{hint}"
        )
    if variant is not None and variant not in component.optional:
        choices = ", ".join(sorted(component.optional)) or "<none>"
        raise InstallError(
            f"component {component_name!r} has no optional group {variant!r}; "
            f"--variant must be one of {choices}"
        )
    return Profile(
        name=component_name,
        path=root / f"<component {component_name}>",
        python=python or _supported_python(component),
        platform=runtime_platform(),
        components={component_name: Selection(placement="in-env", variant=variant)},
        dependencies=(),
        index_url=None,
        extra_index_urls=(),
        lock=None,
        core=True,
        generate_extra=False,
        extra=None,
        description=f"development diagnostic environment for {component_name}",
        synthetic=True,
    )


def resolve_install_target(
    target: str,
    catalog: Catalog,
    *,
    root: Path,
    include_dev: bool = False,
    variant: str | None = None,
) -> Resolution:
    """Resolve a profile name or, when needed, a single component name.

    ``variant`` names the optional group of a single component; a profile
    selects its variants itself, so passing both is a mistake.
    """
    if target in catalog.profiles:
        if variant is not None:
            raise InstallError(
                f"profile {target!r} selects its own variants; --variant applies "
                "only to a single component target"
            )
        profile = catalog.profiles[target]
        if include_dev:
            profile = _with_dev(profile, catalog)
    elif target in catalog.components:
        if include_dev:
            raise InstallError("--dev applies to profiles, not single components")
        profile = component_profile(target, catalog, root=root, variant=variant)
    else:
        known = ", ".join(sorted(catalog.profiles))
        raise InstallError(
            f"unknown profile or component {target!r}; known profiles: {known}"
        )
    core = read_core_dependencies(root) if profile.core else ()
    return resolve(profile, catalog, core_dependencies=core)


def install(
    target: str,
    *,
    root: Path | None = None,
    venv: Path | None = None,
    include_dev: bool = False,
    variant: str | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """Install ``target`` and return the written fingerprint."""
    repo_root = (root or get_repo_root()).resolve()
    catalog = discover(repo_root)
    resolution = resolve_install_target(
        target, catalog, root=repo_root, include_dev=include_dev, variant=variant
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    profile = resolution.profile
    # A component install is a development diagnostic: its synthetic profile
    # comes from the host interpreter rather than a declared envs/<name>.toml,
    # so the fingerprint must say so.
    install_kind = "profile" if target in catalog.profiles else "component"
    core = read_core_dependencies(repo_root) if profile.core else ()
    main_requirements = render_requirements(
        resolution, profile.name, core_dependencies=core
    )
    destination = (venv or default_venv(repo_root, profile)).resolve()
    requirements_path = requirements_file(repo_root, profile, profile.name)
    external = resolution.nonempty_environments()
    external.pop(profile.name, None)

    if dry_run:
        print(main_requirements, end="")
        return {
            "profile": profile.name,
            "venv": str(destination),
            "requirements": main_requirements,
            "external_environments": sorted(external),
        }

    # A lock is only a guarantee while it still covers the manifests. Check
    # before touching the virtualenv so a stale lock fails fast with the
    # command that regenerates it. `--dev` appends packages the lock does not
    # contain, so it installs from the generated requirements instead.
    if not include_dev:
        problems = lock_problems(profile, resolution, repo_root, core_dependencies=core)
        if problems:
            raise InstallError("\n".join(problems))

    existing = read_fingerprint(destination)
    if existing is not None:
        existing_kind = existing.get("install_kind", "profile")
        existing_name = existing.get("profile") or existing.get("component")
        if (existing_kind, existing_name) != (install_kind, profile.name):
            raise InstallError(
                f"{destination} is already installed for {existing_kind} "
                f"{existing_name!r}; environments cannot share a virtualenv "
                f"because their dependencies differ. Install "
                f"{profile.name!r} into its own environment, for example "
                f"`--venv {default_venv(repo_root, profile)}`"
            )

    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(main_requirements, encoding="utf-8")
    external_requirements: dict[str, Path] = {}
    for environment in sorted(external):
        path = requirements_file(repo_root, profile, environment)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            render_requirements(resolution, environment, core_dependencies=core),
            encoding="utf-8",
        )
        external_requirements[environment] = path

    uv = find_uv()
    python = venv_python(destination)
    if not python.exists():
        if verbose:
            print(f"$ {uv} venv --python {profile.python} {destination}")
        run_command([uv, "venv", "--python", profile.python, str(destination)])
        python = venv_python(destination)
    if not python.exists():
        raise InstallError(
            f"{destination} exists but has no Python interpreter; remove it and "
            f"rerun `rpent-env install {target}`"
        )

    # Install the profile's lock when it exists so a checkout with a lock gets
    # the same versions everywhere. A lock covers only the profile closure, so
    # `--dev` (which appends the dev profile's packages) resolves from the
    # generated requirements instead.
    lock = repo_root / profile.lock if profile.lock else None
    using_lock = lock is not None and lock.is_file() and not include_dev
    install_from = lock if using_lock else requirements_path
    install_command = [uv, "pip", "install", "--python", str(python)]
    install_command.extend(index_options(profile))
    for resolved in resolution.main_installed().values():
        for override in resolved.component.overrides:
            install_command.extend(["--override", str(override)])
    install_command.extend(["-r", str(install_from)])
    if verbose:
        print(f"$ {' '.join(install_command)}")
    run_command(install_command)

    if profile.core:
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
        run_command(editable)

    _probe_components(resolution, python, repo_root, verbose=verbose)
    run_command([uv, "pip", "check", "--python", str(python)])

    frozen = run_command([uv, "pip", "freeze", "--python", str(python)], capture=True)
    commit, dirty = source_state(repo_root)
    fingerprint = {
        "schema": 1,
        "install_kind": install_kind,
        # A component diagnostic has no declared profile; record the component
        # instead so `doctor` can rebuild the same synthetic profile.
        "profile": profile.name if install_kind == "profile" else None,
        "component": profile.name if install_kind == "component" else None,
        # Only a lock pins the transitive closure; `--dev` and component
        # diagnostics install resolved versions that a later run may change.
        "reproducible": using_lock,
        "python": _python_version(python),
        "platform": runtime_platform(),
        "source_commit": commit,
        "source_dirty": dirty,
        "components": {
            name: {
                "manifest_sha256": resolved.component.manifest_sha256,
                "placement": resolved.placement,
                "variant": resolved.variant,
                **(
                    {"profile": resolved.env}
                    if resolved.placement == "external-env"
                    else {}
                ),
            }
            for name, resolved in sorted(resolution.components.items())
        },
        "requirements_sha256": requirements_sha256(
            resolution,
            core_dependencies=core,
            include_dev=include_dev,
        ),
        "include_dev": include_dev,
        "freeze_sha256": freeze_sha256(frozen),
        "requirements_file": str(requirements_path.relative_to(repo_root)),
        "external_requirements": {
            environment: str(path.relative_to(repo_root))
            for environment, path in external_requirements.items()
        },
        "lock": str(lock.relative_to(repo_root)) if using_lock else None,
        "installed_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    written = write_fingerprint(destination, fingerprint)
    if verbose:
        print(f"installation fingerprint: {written}")
        if external:
            print("external environments are installed separately:")
            for environment in sorted(external):
                print(f"  rpent-env install {environment}")
    return fingerprint


def index_options(profile: Profile) -> list[str]:
    options: list[str] = []
    if profile.index_url:
        options.extend(["--index-url", profile.index_url])
    for url in profile.extra_index_urls:
        options.extend(["--extra-index-url", url])
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
    profile = resolution.profile
    command = f"rpent-env install {profile.name}"
    selection = profile.components.get(profile.name)
    if profile.synthetic and selection is not None and selection.variant is not None:
        command += f" --variant {selection.variant}"
    return command


def _probe_components(
    resolution: Resolution,
    python: Path,
    root: Path,
    *,
    verbose: bool,
) -> None:
    # This includes deps components: they have no code of their own, but their
    # probe proves the package group a consumer relies on really imported.
    environment = {**os.environ, "PYTHONPATH": str(root)}
    for name, resolved in sorted(resolution.main_installed().items()):
        probe = resolved.component.probe
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
