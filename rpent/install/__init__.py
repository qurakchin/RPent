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

"""Component manifests, install targets, and the ``rpent-install`` installer.

A component is an install boundary: one directory, one ``component.toml``, one
import probe, and its direct dependencies. Every non-robot component is also an
install target under its own name; a robot needs an explicit file in
``installs/targets/<name>.toml``, which also composes several components into
one environment. ``install <target> --with <component>`` adds one more
component to that environment and records it in the same fingerprint. Installed
environments carry
``rpent-install.json`` with the target, the hash of the installation inputs,
and the installed package set, which ``rpent-install doctor`` and run artifacts
use.
"""

from rpent.install.discovery import (
    Catalog,
    discover,
    discover_components,
    discover_targets,
)
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import (
    FINGERPRINT_NAME,
    fingerprint_path,
    read_fingerprint,
    write_fingerprint,
)
from rpent.install.manifest import Component, Target
from rpent.install.require import MissingComponentError, require
from rpent.install.resolve import Resolution, resolve

__all__ = [
    "FINGERPRINT_NAME",
    "Catalog",
    "Component",
    "InstallConfigError",
    "InstallError",
    "MissingComponentError",
    "Target",
    "Resolution",
    "discover",
    "discover_components",
    "discover_targets",
    "fingerprint_path",
    "read_fingerprint",
    "require",
    "resolve",
    "write_fingerprint",
]
