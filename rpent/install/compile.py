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

"""Check component dependencies with a temporary ``uv pip compile`` resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rpent.install.errors import InstallError
from rpent.install.installer import index_options, run_command
from rpent.install.requirements import render_requirements
from rpent.install.resolve import Resolution

# Pin the manylinux baseline instead of uv's default glibc 2.17 target: current
# GPU wheels are published for newer baselines (rerun-sdk for manylinux_2_31,
# Isaac Sim for manylinux_2_35), so a 2.17 baseline cannot resolve them.
DEFAULT_MANYLINUX = "2_31"
PLATFORM_TAGS = {
    "linux-x86_64": "x86_64-manylinux_{baseline}",
    "linux-aarch64": "aarch64-manylinux_{baseline}",
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x86_64": "x86_64-apple-darwin",
}


def compile_resolution(
    resolution: Resolution,
    *,
    root: Path,
    uv: str,
    output: Path,
    python: str,
    platform: str,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Compile one component environment into ``output``.

    ``python`` is the ``major.minor`` interpreter the environment would run.
    """
    platform_template = PLATFORM_TAGS.get(platform)
    if platform_template is None:
        raise InstallError(
            f"unknown platform {platform!r}; known: {', '.join(sorted(PLATFORM_TAGS))}"
        )
    platform_tag = platform_template.format(baseline=DEFAULT_MANYLINUX)
    requirements = render_requirements(resolution, core_dependencies=core_dependencies)
    name = "+".join(resolution.targets)
    with tempfile.TemporaryDirectory(prefix="rpent-requirements-") as directory:
        source = Path(directory) / f"{name}.txt"
        source.write_text(requirements, encoding="utf-8")
        command = [
            uv,
            "pip",
            "compile",
            str(source),
            "--python-version",
            python,
            "--python-platform",
            platform_tag,
            "--no-header",
            "--no-annotate",
            "--output-file",
            str(output),
            *index_options(resolution),
        ]
        for component in resolution.components.values():
            for override in component.overrides:
                # Manifests resolve overrides to absolute paths when they are
                # loaded, so uv's working directory does not matter here.
                command.extend(["--overrides", str(override)])
        # Capture output so a resolution failure reports uv's reason (a missing
        # branch, an unreachable index) instead of only the command line. uv
        # discovers ``[tool.uv]`` from its working directory, so compile in the
        # checkout rather than wherever the CLI was invoked.
        run_command(command, capture=True, cwd=root)
    return output.read_text(encoding="utf-8")


def resolve_resolution(
    resolution: Resolution,
    *,
    root: Path,
    uv: str,
    python: str,
    platform: str,
    core_dependencies: tuple[str, ...] = (),
) -> str:
    """Compile ``resolution`` into a temporary file and return the uv output.

    ``rpent-install check --resolve`` uses this to prove that the declared
    dependencies have a solution; it delegates to :func:`compile_resolution` so
    there is only one resolver.
    """
    with tempfile.TemporaryDirectory(prefix="rpent-resolve-") as directory:
        output = Path(directory) / "requirements.txt"
        return compile_resolution(
            resolution,
            root=root,
            uv=uv,
            output=output,
            python=python,
            platform=platform,
            core_dependencies=core_dependencies,
        )
