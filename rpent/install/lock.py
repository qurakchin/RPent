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

"""Compile and verify per-profile dependency locks with ``uv pip compile``."""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from rpent.install.discovery import Catalog, discover
from rpent.install.errors import InstallError
from rpent.install.installer import find_uv, index_options, run_command
from rpent.install.manifest import Profile
from rpent.install.requirements import read_core_dependencies, render_requirements
from rpent.install.resolve import resolve
from rpent.utils.config import get_repo_root

# Pin the manylinux baseline instead of uv's default glibc 2.17 target: current
# GPU wheels are published for newer baselines (rerun-sdk for manylinux_2_31,
# Isaac Sim for manylinux_2_35), so a 2.17 baseline cannot resolve them. A
# profile raises its baseline with `manylinux` when its components need it.
PLATFORM_TAGS = {
    "linux-x86_64": "x86_64-manylinux_{baseline}",
    "linux-aarch64": "aarch64-manylinux_{baseline}",
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x86_64": "x86_64-apple-darwin",
}


def lock_path(root: Path, profile: Profile) -> Path:
    """Return the profile's declared or conventional lock path."""
    return root / (profile.lock or f"envs/locks/{profile.name}.lock")


def compile_profile(
    profile: Profile,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
    output: Path,
) -> str:
    """Compile one profile's lock into ``output`` and return the lock text."""
    resolution = resolve(
        profile,
        catalog,
        core_dependencies=read_core_dependencies(root) if profile.core else (),
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    platform_template = PLATFORM_TAGS.get(profile.platform)
    if platform_template is None:
        raise InstallError(
            f"profile {profile.name!r} uses unknown platform {profile.platform!r}; "
            f"known: {', '.join(sorted(PLATFORM_TAGS))}"
        )
    platform_tag = platform_template.format(baseline=profile.manylinux)
    requirements = render_requirements(
        resolution,
        profile.name,
        core_dependencies=read_core_dependencies(root) if profile.core else (),
    )
    with tempfile.TemporaryDirectory(prefix="rpent-lock-") as directory:
        source = Path(directory) / f"{profile.name}.txt"
        source.write_text(requirements, encoding="utf-8")
        command = [
            uv,
            "pip",
            "compile",
            str(source),
            "--python-version",
            profile.python,
            "--python-platform",
            platform_tag,
            "--no-header",
            "--no-annotate",
            "--output-file",
            str(output),
            *index_options(profile),
        ]
        for resolved in resolution.main_installed().values():
            for override in resolved.component.overrides:
                command.extend(["--overrides", str(override)])
        # Capture output so a resolution failure reports uv's reason (a missing
        # branch, an unreachable index) instead of only the command line.
        run_command(command, capture=True)
    return output.read_text(encoding="utf-8")


def resolve_profile(
    profile: Profile,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
) -> str:
    """Compile ``profile`` into a temporary file and return the uv output.

    ``rpent-env check --resolve`` uses this to prove that the declared
    dependencies have a solution; it delegates to :func:`compile_profile` so
    there is only one resolver.
    """
    with tempfile.TemporaryDirectory(prefix="rpent-resolve-") as directory:
        output = Path(directory) / f"{profile.name}.txt"
        return compile_profile(profile, catalog, root=root, uv=uv, output=output)


def lock_profiles(
    targets: list[str],
    *,
    root: Path | None = None,
    check: bool = False,
) -> int:
    """Compile or verify locks; return a process exit code."""
    repo_root = (root or get_repo_root()).resolve()
    catalog = discover(repo_root)
    uv = find_uv()
    names = targets or sorted(
        name for name, profile in catalog.profiles.items() if profile.lock
    )
    has_drift = False
    for name in names:
        profile = catalog.profiles.get(name)
        if profile is None:
            raise InstallError(f"unknown profile {name!r}")
        destination = lock_path(repo_root, profile)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not check:
                # Compile into a temporary file: uv reuses an existing output
                # file as its resolution cache, so writing over the old lock can
                # resurrect versions the current index no longer selects and
                # make `--check` disagree with the write.
                with tempfile.TemporaryDirectory(
                    prefix="rpent-lock-write-"
                ) as directory:
                    candidate = Path(directory) / destination.name
                    compile_profile(
                        profile, catalog, root=repo_root, uv=uv, output=candidate
                    )
                    shutil.copyfile(candidate, destination)
                print(f"locked {name}: {destination.relative_to(repo_root)}")
                continue
            with tempfile.TemporaryDirectory(prefix="rpent-lock-check-") as directory:
                candidate = Path(directory) / destination.name
                compile_profile(
                    profile, catalog, root=repo_root, uv=uv, output=candidate
                )
                expected = candidate.read_text(encoding="utf-8")
        except InstallError as exc:
            # One profile that cannot resolve on this host must not hide the
            # state of the others; for example a simulator may need CUDA to lock.
            print(f"lock {name}: FAIL\n  {exc}")
            has_drift = True
            continue
        if not destination.is_file():
            print(f"missing lock: {destination.relative_to(repo_root)}")
            has_drift = True
            continue
        current = destination.read_text(encoding="utf-8")
        if current != expected:
            diff = "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    expected.splitlines(keepends=True),
                    fromfile=str(destination),
                    tofile=f"{destination} (recompiled)",
                )
            )
            print(diff)
            print(f"lock is out of date for {name}; run `rpent-env lock {name}`")
            has_drift = True
        else:
            print(f"lock ok: {name}")
    return 1 if has_drift else 0
