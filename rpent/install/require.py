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

    torch = require("model-sam3", "torch")
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from rpent.install.fingerprint import current_venv, read_fingerprint


class MissingComponentError(ImportError):
    """An optional module is missing from the environment that should own it."""


def _invocation(names: list[str], venv: Path) -> str:
    command = "rpent-install install"
    if names:
        command += f" {' '.join(names)}"
    return f"{command} --venv {venv}"


def _install_hint(component: str) -> str:
    """Return the command that installs ``component`` in this environment.

    Every component installs under its own name, so the missing module's owner
    is enough to name the command: no reverse index from components to
    environments is needed. When the process runs inside an installed
    environment, the command targets that virtualenv and keeps the components
    already requested there.
    """
    venv = current_venv()
    fingerprint = read_fingerprint(venv) if venv is not None else None
    if fingerprint is None:
        return f"install it with `rpent-install install {component}`"
    recorded = fingerprint.get("components") or {}
    requested = [
        item for item in fingerprint.get("requested") or () if isinstance(item, str)
    ]
    if component in recorded:
        names = requested or [component]
        return f"rerun `{_invocation(names, venv)}` to repair the environment"
    environment = fingerprint.get("environment")
    names = [*requested, component] if requested else [component]
    return (
        f"component {component!r} is not part of environment "
        f"{environment!r}; install it with `{_invocation(names, venv)}`"
    )


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
