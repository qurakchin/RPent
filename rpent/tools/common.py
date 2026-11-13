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

"""Compatibility name for the shared file tools.

The implementations live in :mod:`rpent.tools.file_tools`; ``CommonTools`` is
kept for existing imports. ``finish`` belongs to
:class:`~rpent.tools.toolkit.Toolkit`, which registers it once for every run;
robots replace it when their finish policy differs.
"""

from __future__ import annotations

from rpent.tools.file_tools import FileTools


class CommonTools(FileTools):
    """Backward-compatible alias for the run's shared file tools."""


__all__ = ["CommonTools"]
