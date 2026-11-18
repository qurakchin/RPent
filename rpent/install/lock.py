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

"""Compile per-target dependency locks with ``uv pip compile``.

``python -m tests.tooling.lock`` is the maintainer entry point; the compile
mechanics live here so the installer, ``check --resolve``, and the lock tool
share one resolver.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from rpent.install.discovery import Catalog
from rpent.install.errors import InstallError
from rpent.install.installer import index_options, run_command
from rpent.install.manifest import Target
from rpent.install.requirements import (
    read_core_dependencies,
    render_requirements,
)
from rpent.install.resolve import python_accepted, resolve

# Pin the manylinux baseline instead of uv's default glibc 2.17 target: current
# GPU wheels are published for newer baselines (rerun-sdk for manylinux_2_31,
# Isaac Sim for manylinux_2_35), so a 2.17 baseline cannot resolve them. A
# target raises its baseline with `manylinux` when its components need it.
# RPent installs only on linux-x86_64, so the tag has no per-target variant.
PLATFORM_TAG = "x86_64-manylinux_{baseline}"

#: Every lock records the upstream cutoff it was compiled with. ``--check``
#: recompiles at the same instant, so a lock only drifts when its declared
#: inputs change rather than whenever an upstream project publishes a release.
LOCK_TIMESTAMP_PREFIX = "# exclude_newer = "
#: A lock also records the Python minor it resolved for, so an install picks
#: the same interpreter even when the target's request is a range.
LOCK_PYTHON_PREFIX = "# python = "


def _header_value(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def lock_timestamp(text: str) -> str | None:
    """Return the ``exclude_newer`` timestamp declared by a lock, if valid."""
    value = _header_value(text, LOCK_TIMESTAMP_PREFIX)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return value


def lock_python(text: str) -> str | None:
    """Return the Python minor a lock was compiled for, if it records one."""
    return _header_value(text, LOCK_PYTHON_PREFIX)


def new_lock_timestamp() -> str:
    """Return the current UTC instant in lock-header form."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def lock_path(root: Path, target: Target) -> Path:
    """Return the target's declared or conventional lock path."""
    return target.lock_file(root)


def compile_target(
    target: Target,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
    output: Path,
    exclude_newer: str | None = None,
    python: str | None = None,
) -> str:
    """Compile one target's lock into ``output`` and return the lock text.

    ``exclude_newer`` pins the upstream cutoff. ``lock --check`` reads it from
    the existing lock, so the recompiled body is comparable even after a
    release lands upstream; ``lock`` writes the current instant.

    ``python`` is the minor the existing lock records. Reusing it keeps a
    target on the interpreter its checked-in lock was verified with until a
    constraint stops accepting it, instead of silently upgrading every
    environment when a newer minor is supported.
    """
    resolution = resolve(
        target,
        catalog,
        core_dependencies=read_core_dependencies(root) if target.core else (),
    )
    if not resolution.ok:
        raise InstallError("\n".join(resolution.errors))
    if resolution.python is None:
        raise InstallError("\n".join(resolution.errors))
    chosen_python = resolution.python
    if python is not None and python_accepted(resolution, python):
        chosen_python = python
    platform_tag = PLATFORM_TAG.format(baseline=target.manylinux)
    requirements = render_requirements(
        resolution,
        core_dependencies=read_core_dependencies(root) if target.core else (),
    )
    with tempfile.TemporaryDirectory(prefix="rpent-lock-") as directory:
        source = Path(directory) / f"{target.name}.txt"
        source.write_text(requirements, encoding="utf-8")
        command = [
            uv,
            "pip",
            "compile",
            str(source),
            "--python-version",
            chosen_python,
            "--python-platform",
            platform_tag,
            "--no-header",
            "--no-annotate",
            "--output-file",
            str(output),
            *index_options(target),
        ]
        if exclude_newer is not None:
            command.extend(["--exclude-newer", exclude_newer])
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
    text = output.read_text(encoding="utf-8")
    header = f"{LOCK_PYTHON_PREFIX}{chosen_python}\n"
    if exclude_newer is not None:
        header += f"{LOCK_TIMESTAMP_PREFIX}{exclude_newer}\n"
    text = f"{header}{text}"
    output.write_text(text, encoding="utf-8")
    return text


def resolve_target(
    target: Target,
    catalog: Catalog,
    *,
    root: Path,
    uv: str,
) -> str:
    """Compile ``target`` into a temporary file and return the uv output.

    ``tests.tooling.check --resolve`` uses this to prove that the declared
    dependencies have a solution; it delegates to :func:`compile_target` so
    there is only one resolver.
    """
    with tempfile.TemporaryDirectory(prefix="rpent-resolve-") as directory:
        output = Path(directory) / f"{target.name}.txt"
        return compile_target(target, catalog, root=root, uv=uv, output=output)
