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

"""Component manifests, environment profiles, and the ``rpent-env`` installer.

A component is an install boundary: one directory, one ``component.toml``, one
import probe, and its direct dependencies. A profile in ``envs/<name>.toml``
composes components into one supported environment. Installed environments
carry ``rpent-install.json`` with the profile, component manifests, lock, and
freeze hashes used by ``rpent-env doctor`` and run artifacts.
"""

from rpent.install.discovery import (
    Catalog,
    discover,
    discover_components,
    discover_profiles,
)
from rpent.install.errors import InstallConfigError, InstallError
from rpent.install.fingerprint import (
    FINGERPRINT_NAME,
    fingerprint_path,
    read_fingerprint,
    write_fingerprint,
)
from rpent.install.manifest import Component, Profile, Selection
from rpent.install.resolve import Resolution, resolve

__all__ = [
    "FINGERPRINT_NAME",
    "Catalog",
    "Component",
    "InstallConfigError",
    "InstallError",
    "Profile",
    "Resolution",
    "Selection",
    "discover",
    "discover_components",
    "discover_profiles",
    "fingerprint_path",
    "read_fingerprint",
    "resolve",
    "write_fingerprint",
]
