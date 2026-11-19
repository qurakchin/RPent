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

"""Installer units run as though on the platform RPent installs on."""

import pytest


@pytest.fixture(autouse=True)
def supported_platform(monkeypatch):
    """Report ``linux-x86_64`` as this machine's platform.

    Components support that platform unless a manifest says otherwise, so a
    test running on a developer machine of another platform would stop at
    resolution before reaching the behaviour it checks. A test that needs a
    different host installs it explicitly.
    """
    for module in ("rpent.install.installer", "rpent.install.doctor"):
        monkeypatch.setattr(f"{module}.runtime_platform", lambda: "linux-x86_64")
