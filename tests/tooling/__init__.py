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

"""Maintainer and CI tools over the repository's install data.

Run each tool from the repository root with ``python -m tests.tooling.<tool>``:

- ``check``: manifests, closures, variants, placement, and lock coverage.
- ``lock``: compile or verify the profile locks.
- ``layout``: directory structure and import boundaries (K1–K7).
- ``extras``: generate or verify the compatibility extras block.
- ``matrix``: print one runner's profiles or check the partition.
- ``affected``: select the profiles and test directories a change affects.

The tools read the same component manifests and profiles as ``rpent-install``;
the dependency runs only this way, ``tests.tooling`` → ``rpent.install``. They
are not part of the wheel and are never exposed as ``rpent-install``
subcommands.
"""
