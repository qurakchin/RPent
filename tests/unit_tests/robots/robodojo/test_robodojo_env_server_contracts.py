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

"""Lock the RoboDojo env server to the public upstream RoboDojo API.

Upstream RoboDojo has no ``src/collect_client/collect_env`` module (verified
across its git history); the env server must build its environment from the
public task registry instead, or it cannot boot.
"""

from __future__ import annotations

from pathlib import Path

from robots.robodojo import env_server

FORBIDDEN_PRIVATE_API = ("src.collect_client", "create_collect_env")


def test_env_server_imports_without_isaac_sim() -> None:
    assert Path(env_server.__file__).is_file()


def test_env_server_does_not_use_the_private_collect_api() -> None:
    source = Path(env_server.__file__).read_text(encoding="utf-8")

    for forbidden in FORBIDDEN_PRIVATE_API:
        assert forbidden not in source, f"env_server still references {forbidden!r}"
