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
live in ``rpent/env/`` and the model bases in ``capabilities/_base/``. This
module keeps the old import path working for one release; import the new
modules instead.
"""

from importlib import import_module

_ALIASES = {
    "BaseAMClient": "capabilities._base.client",
    "BaseVLAClient": "capabilities._base.client",
    "BaseWAMClient": "capabilities._base.client",
    "BaseAMFacade": "capabilities._base.facade",
    "BaseVLAFacade": "capabilities._base.facade",
    "BaseWAMFacade": "capabilities._base.facade",
    "BaseEnvClient": "rpent.env.client",
    "BaseEnvFacade": "rpent.env.facade",
}

__all__ = sorted(_ALIASES)


def __getattr__(name: str):
    module_name = _ALIASES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)
