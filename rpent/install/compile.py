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

"""Check profile dependencies with a temporary ``uv pip compile`` resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rpent.install.discovery import Catalog
from rpent.install.errors import InstallError
from rpent.install.installer import index_options, run_command
from rpent.install.manifest import Profile
from rpent.install.requirements import (
    read_core_dependencies,
    render_requirements,
)
from rpent.install.resolve import resolve

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


def compile_profile(
    profile: Profile,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
    output: Path,
) -> str:
    """Compile one profile into ``output`` for a dependency resolution check."""
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
    with tempfile.TemporaryDirectory(prefix="rpent-requirements-") as directory:
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
                # Manifests resolve overrides to absolute paths when they are
                # loaded, so uv's working directory does not matter here.
                command.extend(["--overrides", str(override)])
        # Capture output so a resolution failure reports uv's reason (a missing
        # branch, an unreachable index) instead of only the command line. uv
        # discovers ``[tool.uv]`` from its working directory, so compile in the
        # checkout rather than wherever the CLI was invoked.
        run_command(command, capture=True, cwd=root)
    return output.read_text(encoding="utf-8")


def resolve_profile(
    profile: Profile,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
) -> str:
    """Compile ``profile`` into a temporary file and return the uv output.

    ``rpent-install check --resolve`` uses this to prove that the declared
    dependencies have a solution; it delegates to :func:`compile_profile` so
    there is only one resolver.
    """
    with tempfile.TemporaryDirectory(prefix="rpent-resolve-") as directory:
        output = Path(directory) / f"{profile.name}.txt"
        return compile_profile(profile, catalog, root=root, uv=uv, output=output)
