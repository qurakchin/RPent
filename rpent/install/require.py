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


#: Component -> targets whose resolution closure contains it, or ``None`` until
#: the checkout is read for the first failure in this process.
_TARGETS_BY_COMPONENT: dict[str, list[str]] | None = None


def _targets_by_component() -> dict[str, list[str]]:
    """Return the component -> targets index read from the checkout.

    Which targets include a component is a property of the manifests, so read
    them at the point of failure rather than from the fingerprint: an installed
    environment predates targets added afterwards, and a stale reverse index
    would name the wrong repair command. A broken checkout must not mask the
    missing import that triggered the hint, so failures leave an empty index.
    """
    global _TARGETS_BY_COMPONENT
    if _TARGETS_BY_COMPONENT is not None:
        return _TARGETS_BY_COMPONENT
    index: dict[str, list[str]] = {}
    try:
        from rpent.install.discovery import discover
        from rpent.install.resolve import resolve
        from rpent.utils.config import get_repo_root

        catalog = discover(get_repo_root())
        included: dict[str, set[str]] = {}
        for name, target in catalog.targets.items():
            resolution = resolve(target, catalog)
            if not resolution.ok:
                continue
            for component in resolution.components:
                included.setdefault(component, set()).add(name)
        index = {name: sorted(targets) for name, targets in included.items()}
    except Exception:  # noqa: BLE001 - the hint must not replace the import error
        index = {}
    _TARGETS_BY_COMPONENT = index
    return index


def _install_hint(component: str) -> str:
    venv = current_venv()
    fingerprint = read_fingerprint(venv) if venv is not None else None
    if fingerprint is None:
        return (
            f"install the environment that provides component {component!r}: "
            f"run `rpent-install list` and install a target that includes it"
        )
    target = fingerprint.get("target")
    if not target:
        # A fingerprint written before targets became the only install unit
        # records no target; name the component without inventing one.
        return (
            f"install the environment that provides component {component!r}: "
            f"run `rpent-install list` and install a target that includes it"
        )
    placement = fingerprint.get("components", {}).get(component)
    if placement is None:
        targets = _targets_by_component().get(component, [])
        if targets:
            return (
                f"component {component!r} is not part of target {target!r}; "
                f"install one of the targets that includes it: "
                f"{', '.join(targets)}"
            )
        return (
            f"component {component!r} is not part of target {target!r}; "
            "install a target that includes it"
        )
    if placement.get("placement") == "remote":
        return (
            f"component {component!r} runs outside target {target!r}; install its "
            "own target on that host, then rerun "
            f"`rpent-install install {target}` to restore the client"
        )
    return f"rerun `rpent-install install {target}` to repair the environment"


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
