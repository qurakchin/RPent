#!/usr/bin/env python3
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

"""Assign every environment profile to the nightly install runner that tests it.

Profiles are discovered, but the nightly workflow needs a static matrix. The
partition below is authored on purpose: a generated matrix would follow the
profiles it is supposed to cover, so a profile that nobody classified would
quietly install nowhere. ``--check`` compares the table with
``envs/*.toml`` and fails when a profile is missing or no longer exists, which
makes adding a profile also a decision about where it is installed.

Hosted runners install the profiles whose lock pulls no CUDA packages; the GPU
runner installs everything that does.

Usage::

    python scripts/env_matrix.py --check              # CI
    python scripts/env_matrix.py --runner hosted      # workflow matrix
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpent.install.discovery import discover_profiles  # noqa: E402

#: CPU-only profiles: installable on a hosted runner within its disk and time
#: limits.
HOSTED = ("dev", "geometry-eval", "minimal", "yam-real")

#: Profiles that resolve CUDA packages; they need the embodied GPU runner.
GPU = (
    "dual-franka-real",
    "franka-real",
    "libero-openpi-external",
    "libero-plus",
    "libero-pro",
    "libero-pro-flywheel",
    "libero-pro-molmo",
    "libero-sim",
    "molmo-server",
    "openpi-server",
    "robocasa-sim",
    "robodojo-sim",
    "robotwin-sim",
    "sam3-server",
)

MATRICES = {"hosted": HOSTED, "gpu": GPU}


def problems(
    profiles: dict[str, object], matrices: dict[str, tuple[str, ...]] | None = None
) -> list[str]:
    """Return every way the partition disagrees with ``profiles``."""
    table = MATRICES if matrices is None else matrices
    found: list[str] = []
    for runner, names in table.items():
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            found.append(f"{runner} lists profile {name!r} more than once")
        for name in names:
            if name not in profiles:
                found.append(
                    f"{runner} lists profile {name!r}, but envs/{name}.toml does "
                    "not exist; remove it from scripts/env_matrix.py"
                )
    assigned = {name for names in table.values() for name in names}
    for name in sorted(assigned):
        runners = [runner for runner, names in table.items() if name in names]
        if len(runners) > 1:
            found.append(
                f"profile {name!r} is assigned to both "
                f"{' and '.join(sorted(set(runners)))}; keep it on one runner"
            )
    for name in sorted(set(profiles) - assigned):
        found.append(
            f"profile {name!r} (envs/{name}.toml) is not installed by any nightly "
            "runner; add it to HOSTED or GPU in scripts/env_matrix.py"
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        choices=sorted(MATRICES),
        help="print the profiles for one runner as a JSON array",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the table and envs/*.toml disagree",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if not args.check and args.runner is None:
        parser.error("pass --check or --runner")
    if args.check:
        found = problems(discover_profiles(args.root))
        for problem in found:
            print(f"error: {problem}", file=sys.stderr)
        if found:
            return 1
    if args.runner is not None:
        # Read the table without loading the profiles: the workflow needs the
        # matrix before any install runs, and --check owns the drift check.
        print(json.dumps(list(MATRICES[args.runner])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
