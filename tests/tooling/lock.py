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

"""Compile or verify the optional reproduction locks under ``tests/locks``.

``--check`` recompiles each lock at the cutoff recorded in its header, so a
lock drifts only when its declared inputs change rather than whenever an
upstream project publishes a release. Without ``--check`` the lock is rewritten
with the current cutoff. Installation never reads these locks.

Usage::

    python -m tests.tooling.lock --all
    python -m tests.tooling.lock sim-robotwin --check
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
import tempfile
from pathlib import Path

from rpent.install.discovery import discover, environment_names, requested_components
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.installer import find_uv
from rpent.install.lock import (
    LOCK_TIMESTAMP_PREFIX,
    compile_environment,
    lock_path,
    lock_python,
    lock_timestamp,
    new_lock_timestamp,
)
from rpent.install.requirements import read_requirement_text

REPO_ROOT = Path(__file__).resolve().parents[2]


def compile_locks(
    environments: list[str],
    *,
    root: Path,
    check: bool = False,
) -> int:
    """Compile or verify locks; return a process exit code."""
    catalog = discover(root)
    uv = find_uv()
    # Locks are optional reproduction artifacts; every checked-in lock lives
    # under ``tests/locks/<environment>.lock``. Installing never reads a lock.
    names = environments or list(environment_names(catalog.components))
    has_drift = False
    for name in names:
        requested = requested_components(name, catalog.components)
        destination = lock_path(root, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Keep the interpreter the checked-in lock was verified with while its
        # constraints still accept it, so regenerating does not silently move
        # every environment to a newer Python minor.
        try:
            previous_text = (
                read_requirement_text(destination) if destination.is_file() else None
            )
        except InstallConfigError:
            previous_text = None
        previous_python = (
            lock_python(previous_text) if previous_text is not None else None
        )
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
                    compile_environment(
                        requested,
                        catalog,
                        root=root,
                        uv=uv,
                        output=candidate,
                        exclude_newer=new_lock_timestamp(),
                        python=previous_python,
                    )
                    shutil.copyfile(candidate, destination)
                print(f"locked {name}: {destination.relative_to(root)}")
                continue
            if not destination.is_file():
                print(f"missing lock: {destination.relative_to(root)}")
                has_drift = True
                continue
            try:
                current = read_requirement_text(destination)
            except InstallConfigError as exc:
                # A corrupted lock must not hide the state of the other environments.
                print(f"lock {name}: FAIL\n  {exc}")
                has_drift = True
                continue
            if current is None:
                print(
                    f"cannot read {destination.relative_to(root)}; check that "
                    "it is a readable file"
                )
                has_drift = True
                continue
            timestamp = lock_timestamp(current)
            if timestamp is None:
                print(
                    f"lock {name}: FAIL\n  "
                    f"{destination.relative_to(root)} has no "
                    f"'{LOCK_TIMESTAMP_PREFIX.strip()}' header; regenerate it "
                    f"with `python -m tests.tooling.lock {name}`"
                )
                has_drift = True
                continue
            with tempfile.TemporaryDirectory(prefix="rpent-lock-check-") as directory:
                candidate = Path(directory) / destination.name
                compile_environment(
                    requested,
                    catalog,
                    root=root,
                    uv=uv,
                    output=candidate,
                    exclude_newer=timestamp,
                    python=previous_python,
                )
                expected = candidate.read_text(encoding="utf-8")
        except (InstallConfigError, InstallError) as exc:
            # One environment that cannot resolve on this host must not hide the
            # state of the others; for example a simulator may need CUDA to lock.
            print(f"lock {name}: FAIL\n  {exc}")
            has_drift = True
            continue
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
            print(
                f"lock is out of date for {name}; run `python -m tests.tooling.lock {name}`"
            )
            has_drift = True
        else:
            print(f"lock ok: {name}")
    return 1 if has_drift else 0


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Compile locks, or verify them with ``--check``."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.tooling.lock",
        description="Compile or verify the checked-in environment locks.",
    )
    parser.add_argument("environments", nargs="*", help="environment names to lock")
    parser.add_argument(
        "--all",
        action="store_true",
        help="lock every environment",
    )
    parser.add_argument(
        "--check", action="store_true", help="fail when a lock is out of date"
    )
    args = parser.parse_args(argv)
    if not args.all and not args.environments:
        parser.error("pass an environment name or --all")
    try:
        return compile_locks(args.environments, root=root, check=args.check)
    except (InstallConfigError, InstallError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(root=Path.cwd()))
