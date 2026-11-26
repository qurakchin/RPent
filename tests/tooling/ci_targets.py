# Copyright 2026 The RPent Authors.
"""Select the clean builds and simulator suites affected by a Git diff."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SUITES = {
    "robot-libero": ["libero", "libero-pro"],
    "robot-libero_plus": ["libero-plus"],
    "robot-robocasa": ["robocasa"],
    "robot-robotwin": ["robotwin"],
    "robot-robodojo": ["robodojo"],
    "robot-robolab": ["robolab"],
}
# Runtime integrations that also exercise an optional external model service.
OPTIONAL = {
    "apxinf": {"robot-libero"},
    "cosmos_policy": {"robot-libero"},
    "cosmos3": {"robot-libero"},
    "fast_wam": {"robot-libero", "robot-robotwin"},
    "uniwam": {"robot-libero", "robot-robotwin"},
    "xpolicylab": {"robot-robodojo"},
}


def targets(paths: list[str], root: Path) -> tuple[list[str], list[str]]:
    """Map shared code to all suites and component code to its consumers."""
    manifests = {}
    owners = {}
    for pattern in ("robots/*/component.toml", "components/*/*/component.toml"):
        for path in root.glob(pattern):
            manifest = tomllib.loads(path.read_text())
            owners[path.parent.relative_to(root).as_posix()] = manifest["name"]
            manifests[manifest["name"]] = manifest.get("requires", [])
    users = {}
    for robot in SUITES:
        pending = [robot]
        seen = set()
        while pending:
            name = pending.pop()
            if name not in seen:
                seen.add(name)
                users.setdefault(name, set()).add(robot)
                pending.extend(manifests.get(name, []))

    selected = set()
    for filename in paths:
        name = filename.removeprefix("tests/unit_tests/")
        parts = name.split("/")
        if (
            name.startswith(("docs/", ".agents/", ".claude/"))
            or name.endswith((".md", ".rst"))
            and not name.startswith(("robots/", "rpent/", "components/"))
        ):
            continue
        if name.startswith("tests/e2e_tests/") and len(parts) > 3:
            name = "robots/" + parts[2] + "/" + "/".join(parts[3:])
        component = next(
            (owner for owner in owners if name.startswith(owner + "/")), None
        )
        if component:
            selected.update(users.get(owners[component], ()))
            if component in {"robots/libero", "components/sim/libero"}:
                selected.add("robot-libero_plus")
            if component.startswith("components/models/"):
                selected.update(OPTIONAL.get(component.split("/")[-1], ()))
        elif name.startswith(
            (
                "rpent/",
                "components/",
                "robots/",
                "tests/e2e_tests/",
                ".github/workflows/",
            )
        ) or name in {
            "setup.py",
            "pyproject.toml",
            "MANIFEST.in",
            "rpent-install.sh",
            "tests/tooling/ci_targets.py",
            "tooling/test_ci_targets.py",
            "tooling/test_tool_coverage.py",
        }:
            selected.update(SUITES)
    builds = [component for component in SUITES if component in selected]
    return builds, [suite for component in builds for suite in SUITES[component]]


if __name__ == "__main__":
    base, head = sys.argv[1:]
    if base and set(base) != {"0"}:
        raw = subprocess.check_output(
            ["git", "diff", "--no-renames", "--name-only", "-z", base, head]
        )
        paths = [os.fsdecode(path) for path in raw.split(b"\0") if path]
    else:
        paths = ["rpent-install.sh"]
    builds, suites = targets(paths, Path.cwd())
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for label, values in (("builds", builds), ("suites", suites)):
            print(f"{label}={json.dumps(values)}", file=output)
            print(f"{label}: {', '.join(values) or 'none'}")
