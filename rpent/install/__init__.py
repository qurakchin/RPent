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

"""Component manifests and the ``rpent-install`` installer.

A component is an install boundary: one directory, one ``component.toml``, one
import probe, and its direct dependencies. Every component is installable under
its own name, and a robot's ``requires`` names the simulator, models, and tools
it runs with, so the standard composition lives beside the code it binds.

``rpent-install install a b`` creates one environment from those components;
with no component it installs the core-only ``minimal`` environment. Installed
environments carry ``rpent-install.json`` with the environment name, the hash of
the installation inputs, and the installed package set, which
``rpent-install doctor`` and run artifacts use.
"""

from rpent.install.discovery import (
    Catalog,
    discover,
    discover_components,
    environment_names,
)
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import (
    FINGERPRINT_NAME,
    fingerprint_path,
    read_fingerprint,
    write_fingerprint,
)
from rpent.install.manifest import MINIMAL_ENVIRONMENT, Component, environment_name
from rpent.install.require import MissingComponentError, require
from rpent.install.resolve import Resolution, resolve

__all__ = [
    "FINGERPRINT_NAME",
    "MINIMAL_ENVIRONMENT",
    "Catalog",
    "Component",
    "InstallConfigError",
    "InstallError",
    "MissingComponentError",
    "Resolution",
    "discover",
    "discover_components",
    "environment_name",
    "environment_names",
    "fingerprint_path",
    "read_fingerprint",
    "require",
    "resolve",
    "write_fingerprint",
]
