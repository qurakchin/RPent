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

"""Report a missing optional dependency as a component installation error.

Components declare their packages in ``component.toml``; importing them
directly at the point of use keeps core imports working without every robot
extra installed. This guard replaces local ``try: import ... except
ImportError: ... = None`` fallbacks with one actionable message::

    torch = require("sam3", "torch")
"""

from __future__ import annotations

import importlib
from types import ModuleType

from rpent.install.fingerprint import current_venv, read_fingerprint


class MissingComponentError(ImportError):
    """An optional module is missing from the environment that should own it."""


def _install_hint(component: str) -> str:
    venv = current_venv()
    fingerprint = read_fingerprint(venv) if venv is not None else None
    if fingerprint is None:
        return (
            f"install the environment that provides component {component!r}: "
            f"run `rpent-install list` and install a profile that includes it"
        )
    profile = fingerprint.get("profile")
    if not profile:
        # A fingerprint written before profiles became the only install target
        # records no profile; name the component without inventing one.
        return (
            f"install the environment that provides component {component!r}: "
            f"run `rpent-install list` and install a profile that includes it"
        )
    placement = fingerprint.get("components", {}).get(component)
    if placement is None:
        profiles = fingerprint.get("component_profiles", {}).get(component, [])
        if profiles:
            return (
                f"component {component!r} is not part of profile {profile!r}; "
                f"install one of the profiles that includes it: "
                f"{', '.join(profiles)}"
            )
        return (
            f"component {component!r} is not part of profile {profile!r}; "
            "install a profile that includes it"
        )
    if placement.get("placement") == "remote":
        return (
            f"component {component!r} runs outside profile {profile!r}; install its "
            "own profile on that host, then rerun "
            f"`rpent-install install {profile}` to restore the client"
        )
    return f"rerun `rpent-install install {profile}` to repair the environment"


def require(component: str, module: str) -> ModuleType:
    """Import ``module`` or raise an error naming ``component`` and its install.

    Raises:
        MissingComponentError: the module is unavailable in this environment.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingComponentError(
            f"component {component!r} requires {module!r}, which is not "
            f"importable in this environment; {_install_hint(component)}"
        ) from exc
