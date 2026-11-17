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

"""Assign every install profile to the runner that installs it in full CI.

Profiles are discovered, but the workflow needs a static matrix. The partition
below is authored on purpose: a generated matrix would follow the profiles it
is supposed to cover, so a profile that nobody classified would quietly install
nowhere. ``--check`` compares the table with ``installs/profiles/*.toml`` and
fails when a profile is missing or no longer exists, which makes adding a
profile also a decision about where it is installed.

Hosted runners install the profiles whose dependencies pull no CUDA packages; the GPU
runner installs everything that does.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpent.install.discovery import discover_profiles

REPO_ROOT = Path(__file__).resolve().parents[2]

#: CPU-only profiles: installable on a hosted runner within its disk and time
#: limits.
HOSTED = ("dev", "minimal", "unit-cpu", "yam-real")

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
                    f"{runner} lists profile {name!r}, but "
                    f"installs/profiles/{name}.toml does not exist; remove it "
                    "from rpent/install/matrix.py"
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
            f"profile {name!r} (installs/profiles/{name}.toml) is not installed "
            "by any runner; add it to HOSTED or GPU in rpent/install/matrix.py"
        )
    return found


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the partition or print one runner's profiles as JSON."""
    parser = argparse.ArgumentParser(
        prog="rpent-install matrix",
        description="Assign profiles to the runner that installs them.",
    )
    parser.add_argument(
        "--runner",
        choices=sorted(MATRICES),
        help="print the profiles for one runner as a JSON array",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the table and installs/profiles disagree",
    )
    args = parser.parse_args(argv)

    if not args.check and args.runner is None:
        parser.error("pass --check or --runner")
    if args.check:
        found = problems(discover_profiles(root))
        for problem in found:
            print(f"error: {problem}", file=sys.stderr)
        if found:
            return 1
    if args.runner is not None:
        # Read the table without loading the profiles: the workflow needs the
        # matrix before any install runs, and --check owns the drift check.
        print(json.dumps(list(MATRICES[args.runner])))
    return 0
