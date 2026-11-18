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

"""Assign every install target to the runner that installs it in full CI.

Targets are discovered, but the workflow needs a static matrix. The partition
below is authored on purpose: a generated matrix would follow the targets it is
supposed to cover, so a target that nobody classified would quietly install
nowhere. ``--check`` compares the table with ``installs/targets/*.toml``,
``tests/targets/*.toml`` and the target every component forms, and fails when an
entry is missing or no longer exists, which makes adding a component or target
also a decision about where it is installed.

Hosted runners install the targets whose lock pulls no CUDA packages; the GPU
runner installs everything that does.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpent.install.discovery import discover_targets

REPO_ROOT = Path(__file__).resolve().parents[2]

#: CPU-only targets: installable on a hosted runner within its disk and time
#: limits.
HOSTED = (
    "apxinf",
    "cosmos3",
    "cosmos_policy",
    "dev",
    "fast_wam",
    "geometry",
    "minimal",
    "tool-geometry",
    "unit-cpu",
    "uniwam",
    "xpolicylab",
    "yam",
)

#: Targets that resolve CUDA packages; they need the embodied GPU runner.
GPU = (
    "dual_franka",
    "franka",
    "molmo",
    "openpi",
    "robocasa",
    "robodojo",
    "robot-dual_franka",
    "robot-franka",
    "robot-libero_pro",
    "robot-robodojo",
    "robot-yam",
    "robotwin",
    "sam3",
    "sim-libero_plus",
    "sim-libero_pro",
    "sim-libero_standard",
    "tool-flywheel",
)

MATRICES = {"hosted": HOSTED, "gpu": GPU}


def problems(
    targets: dict[str, object],
    matrices: dict[str, tuple[str, ...]] | None = None,
    *,
    root: Path = REPO_ROOT,
) -> list[str]:
    """Return every way the partition disagrees with ``targets``."""
    table = MATRICES if matrices is None else matrices
    found: list[str] = []
    for runner, names in table.items():
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            found.append(f"{runner} lists target {name!r} more than once")
        for name in names:
            if name not in targets:
                found.append(
                    f"{runner} lists target {name!r}, but no target file "
                    f"declares it; remove it from tests/tooling/matrix.py"
                )
    assigned = {name for names in table.values() for name in names}
    for name in sorted(assigned):
        runners = [runner for runner, names in table.items() if name in names]
        if len(runners) > 1:
            found.append(
                f"target {name!r} is assigned to both "
                f"{' and '.join(sorted(set(runners)))}; keep it on one runner"
            )
    for name in sorted(set(targets) - assigned):
        path = getattr(targets[name], "path", None)
        declared = (
            path.relative_to(root)
            if isinstance(path, Path) and path.is_relative_to(root)
            else name
        )
        found.append(
            f"target {name!r} ({declared}) is not installed by any runner; "
            "add it to HOSTED or GPU in tests/tooling/matrix.py"
        )
    return found


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    """Check the partition or print one runner's targets as JSON."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.tooling.matrix",
        description="Assign targets to the runner that installs them.",
    )
    parser.add_argument(
        "--runner",
        choices=sorted(MATRICES),
        help="print the targets for one runner as a JSON array",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the table and the checked-in targets disagree",
    )
    args = parser.parse_args(argv)

    if not args.check and args.runner is None:
        parser.error("pass --check or --runner")
    if args.check:
        found = problems(discover_targets(root), root=root)
        for problem in found:
            print(f"error: {problem}", file=sys.stderr)
        if found:
            return 1
    if args.runner is not None:
        # Read the table without loading the targets: the workflow needs the
        # matrix before any install runs, and --check owns the drift check.
        print(json.dumps(list(MATRICES[args.runner])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
