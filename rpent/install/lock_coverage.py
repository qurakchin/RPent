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

"""Check that a profile's declared lock still satisfies its requirements.

``rpent-env lock`` compiles a lock from the profile's requirement inputs, but
the lock does not record that input. Install therefore verifies the cheap
invariant directly: every direct requirement is present in the lock and the
locked pin still satisfies it. A manifest that changes an unpinned or loosely
pinned dependency without changing the lock is caught here.

Requirements guarded by an environment marker are evaluated against the
profile's declared target, not the host: a lock holds only the line that
applies to the interpreter and platform it was compiled for, so a marker group
for another target is not expected to be present. The profile pins a minor
Python version, so ``python_full_version`` markers assume patch level ``0``;
markers that test a value the profile does not declare are reported instead of
being silently skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

from packaging.markers import Marker, UndefinedEnvironmentName
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from rpent.install.manifest import Profile
from rpent.install.requirements import environment_dependencies
from rpent.install.resolve import Resolution

#: Marker values derived from ``Profile.platform``. A platform outside this
#: table cannot be mapped to a lock target, so the profile is reported instead
#: of guessing at its markers.
PLATFORM_MARKERS = {
    "linux-x86_64": {
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
    },
    "linux-aarch64": {
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "aarch64",
    },
    "darwin-arm64": {
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "platform_machine": "arm64",
    },
    "darwin-x86_64": {
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "platform_machine": "x86_64",
    },
}


def _marker_environment(profile: Profile) -> tuple[dict[str, str] | None, str | None]:
    """Return the marker values for the profile's target, or an error."""
    values = PLATFORM_MARKERS.get(profile.platform)
    if values is None:
        return None, (
            f"profile {profile.name!r} targets {profile.platform!r}, which has no "
            f"lock marker mapping; use one of "
            f"{', '.join(sorted(PLATFORM_MARKERS))}"
        )
    python_full = f"{profile.python}.0"
    return {
        **values,
        "os_name": "posix",
        "python_version": profile.python,
        "python_full_version": python_full,
        "implementation_name": "cpython",
        "implementation_version": python_full,
        "platform_python_implementation": "CPython",
    }, None


#: Marker variables defined by PEP 508.
_MARKER_VARIABLES = (
    "extra",
    "implementation_name",
    "implementation_version",
    "os_name",
    "platform_machine",
    "platform_python_implementation",
    "platform_release",
    "platform_system",
    "platform_version",
    "python_full_version",
    "python_version",
    "sys_platform",
)


def _marker_variables(marker: Marker) -> list[str]:
    """Return every PEP 508 variable named in a marker expression.

    ``Marker`` does not expose its parsed tree, so the expression is matched
    against the finite PEP 508 vocabulary rather than a private attribute;
    quoted values are removed first so they cannot look like variables.
    """
    text = re.sub(r"'[^']*'|\"[^\"]*\"", "", str(marker))
    return [name for name in _MARKER_VARIABLES if re.search(rf"\b{name}\b", text)]


def _marker_applies(
    requirement: Requirement, environment: dict[str, str]
) -> tuple[bool | None, str | None]:
    """Return whether ``requirement`` applies to the profile target.

    A marker that uses a variable the profile does not declare cannot be
    decided; report it rather than skipping the requirement, because skipping
    would let a missing package pass the coverage check. ``Marker.evaluate``
    fills unknown names from the host, so the variables are checked first.
    """
    marker = requirement.marker
    unknown = sorted(set(_marker_variables(marker)) - set(environment))
    if unknown:
        return None, (
            f"{requirement} uses marker {marker}, which needs "
            f"{', '.join(unknown)}; the profile target does not declare it. "
            "Extend PLATFORM_MARKERS or drop the marker"
        )
    try:
        return marker.evaluate(environment), None
    except UndefinedEnvironmentName as exc:
        return None, (
            f"{requirement} uses marker {marker}, which the profile target "
            f"cannot evaluate ({exc}); extend PLATFORM_MARKERS or drop the marker"
        )


def _requirement(value: str) -> Requirement | None:
    try:
        return Requirement(value)
    except InvalidRequirement:
        return None


def _locked_version(requirement: Requirement) -> Version | None:
    """Return the exact version a lock line pins, if any."""
    for specifier in requirement.specifier:
        if specifier.operator in {"==", "==="} and "*" not in specifier.version:
            try:
                return Version(specifier.version)
            except InvalidVersion:
                return None
    return None


def _url_base(url: str) -> str:
    """Return a direct URL without its VCS revision.

    Locked VCS requirements resolve a branch or tag to a commit, so comparing
    the full URL would report every lock as stale. The repository is the part
    that must not change.
    """
    value = url.strip()
    if value.startswith("git+"):
        value = value[4:]
    return value.rsplit("@", 1)[0].rstrip("/").lower()


def parse_lock(text: str) -> dict[str, Requirement]:
    """Return the lock's requirements keyed by canonical package name."""
    entries: dict[str, Requirement] = {}
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith(("#", "-")):
            continue
        requirement = _requirement(value)
        if requirement is None:
            continue
        entries[canonicalize_name(requirement.name)] = requirement
    return entries


def lock_problems(
    profile: Profile,
    resolution: Resolution,
    root: Path,
    *,
    core_dependencies: tuple[str, ...] = (),
) -> list[str]:
    """Return every way the profile's lock disagrees with its requirements.

    An undeclared lock is not a problem; a declared but missing or stale lock
    is.
    """
    if profile.lock is None:
        return []
    path = root / profile.lock
    if not path.is_file():
        return [
            f"profile {profile.name!r} declares lock {profile.lock}, but the file "
            f"does not exist; run `rpent-env lock {profile.name}`"
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read {profile.lock}: {exc}"]
    entries = parse_lock(text)
    problems: list[str] = []
    markers, marker_problem = _marker_environment(profile)
    if marker_problem is not None:
        problems.append(marker_problem)
    for value in environment_dependencies(
        resolution, profile.name, core_dependencies=core_dependencies
    ):
        requirement = _requirement(value)
        if requirement is None:
            continue
        if requirement.marker is not None:
            if markers is None:
                # The profile problem above is the actionable one; do not add a
                # second error per marker-scoped requirement.
                continue
            applies, problem = _marker_applies(requirement, markers)
            if problem is not None:
                problems.append(problem)
                continue
            if not applies:
                continue
        package = canonicalize_name(requirement.name)
        locked = entries.get(package)
        if locked is None:
            problems.append(
                f"{profile.lock} does not cover {package!r} ({value}); "
                f"run `rpent-env lock {profile.name}`"
            )
            continue
        if requirement.url:
            if _url_base(str(requirement.url)) != _url_base(str(locked.url or "")):
                problems.append(
                    f"{profile.lock} pins {package!r} from "
                    f"{locked.url or 'an index'}, but the manifest requires "
                    f"{requirement.url}; run `rpent-env lock {profile.name}`"
                )
            continue
        version = _locked_version(locked)
        if version is None:
            problems.append(
                f"{profile.lock} does not pin a version for {package!r}; "
                f"run `rpent-env lock {profile.name}`"
            )
        elif requirement.specifier and not requirement.specifier.contains(
            version, prereleases=True
        ):
            problems.append(
                f"{profile.lock} pins {package}=={version}, which does not satisfy "
                f"{value}; run `rpent-env lock {profile.name}`"
            )
    return problems
