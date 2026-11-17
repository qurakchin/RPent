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

"""Compatibility aliases for the environment and model base classes.

The implementations moved out of ``rpent/robots/components/``: the env bases
live in ``rpent/env/`` and the model bases in ``rpent/models/``. This module
keeps the old import paths for these classes working for one release; import
the new modules instead. Other modules that used to live here, such as the
per-model clients, have no alias.
"""

import sys
import types
from importlib import import_module

_ALIASES = {
    "BaseAMClient": "rpent.models.client",
    "BaseVLAClient": "rpent.models.client",
    "BaseWAMClient": "rpent.models.client",
    "BaseAMFacade": "rpent.models.facade",
    "BaseVLAFacade": "rpent.models.facade",
    "BaseWAMFacade": "rpent.models.facade",
    "BaseEnvClient": "rpent.env.client",
    "BaseEnvFacade": "rpent.env.facade",
}

#: The submodules that held these classes, mapped to the module that replaced
#: them and the names both modules export.
_MODULE_ALIASES = {
    "am_client_base": (
        "rpent.models.client",
        ("BaseAMClient", "BaseVLAClient", "BaseWAMClient"),
    ),
    "am_facade_base": (
        "rpent.models.facade",
        ("BaseAMFacade", "BaseVLAFacade", "BaseWAMFacade", "WAMAdapterSpec"),
    ),
    "env_client_base": ("rpent.env.client", ("BaseEnvClient",)),
    "env_facade_base": ("rpent.env.facade", ("BaseEnvFacade",)),
}

__all__ = sorted(_ALIASES)


def __getattr__(name: str):
    module_name = _ALIASES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def _install_module_aliases() -> None:
    """Register the removed submodule names so old imports resolve."""
    for suffix, (target, names) in _MODULE_ALIASES.items():
        module_name = f"{__name__}.{suffix}"
        if module_name in sys.modules:
            continue
        source = import_module(target)
        module = types.ModuleType(module_name, source.__doc__)
        for name in names:
            setattr(module, name, getattr(source, name))
        sys.modules[module_name] = module


_install_module_aliases()
