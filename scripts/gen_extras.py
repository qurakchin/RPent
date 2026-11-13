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

"""Regenerate the compatibility extras and uv conflict matrix in pyproject.toml.

The source of truth is component manifests and ``envs/*.toml``. This script
keeps ``pip install -e ".[<extra>]"`` working for one compatibility release.

Usage::

    python scripts/gen_extras.py --write
    python scripts/gen_extras.py --check   # CI
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rpent.install.discovery import discover  # noqa: E402
from rpent.install.extras import generate, replace_block  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="gen_extras.py")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the generated block in pyproject.toml.",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero when pyproject.toml is out of date (default).",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=REPO_ROOT / "pyproject.toml",
        help="pyproject.toml to update or verify.",
    )
    args = parser.parse_args()
    catalog = discover(REPO_ROOT)
    generated = generate(catalog)
    current = args.pyproject.read_text(encoding="utf-8")
    updated = replace_block(current, generated)
    if args.write:
        if updated != current:
            args.pyproject.write_text(updated, encoding="utf-8")
            print(f"updated {args.pyproject}")
        else:
            print(f"{args.pyproject} already up to date")
        return 0
    if updated != current:
        print(
            f"{args.pyproject} is out of date with component manifests; "
            "run `python scripts/gen_extras.py --write`",
            file=sys.stderr,
        )
        return 1
    print(f"{args.pyproject} extras and conflicts are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
