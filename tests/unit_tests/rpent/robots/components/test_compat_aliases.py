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

"""The removed ``rpent.robots.components`` submodules still resolve."""

import importlib

import pytest

#: Removed submodule, the module that replaced it, and the names it exported.
ALIASED_MODULES = [
    (
        "am_client_base",
        "rpent.models.client",
        ("BaseAMClient", "BaseVLAClient", "BaseWAMClient"),
    ),
    (
        "am_facade_base",
        "rpent.models.facade",
        ("BaseAMFacade", "BaseVLAFacade", "BaseWAMFacade", "WAMAdapterSpec"),
    ),
    ("env_client_base", "rpent.env.client", ("BaseEnvClient",)),
    ("env_facade_base", "rpent.env.facade", ("BaseEnvFacade",)),
]


@pytest.mark.parametrize(("removed", "target", "names"), ALIASED_MODULES)
def test_removed_submodules_resolve_to_the_new_classes(removed, target, names):
    old = importlib.import_module(f"rpent.robots.components.{removed}")
    new = importlib.import_module(target)

    for name in names:
        assert getattr(old, name) is getattr(new, name)


def test_package_attributes_match_the_module_aliases():
    from rpent.robots.components import BaseAMClient
    from rpent.robots.components.am_client_base import BaseAMClient as from_module

    assert BaseAMClient is from_module
