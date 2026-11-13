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
"""

from __future__ import annotations

from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from rpent.install.manifest import Profile
from rpent.install.requirements import environment_dependencies
from rpent.install.resolve import Resolution


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
    for value in environment_dependencies(
        resolution, profile.name, core_dependencies=core_dependencies
    ):
        requirement = _requirement(value)
        if requirement is None or requirement.marker is not None:
            # Marker-scoped pins select a wheel per interpreter; the lock holds
            # only the line that applies to its target Python.
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
