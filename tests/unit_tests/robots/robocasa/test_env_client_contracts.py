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

"""RoboCasa env client execution-boundary contracts."""

from __future__ import annotations

from robots.robocasa.env_client import RoboCasaEnvClient
from rpent.tools.execution import track_execution


class _Rpc:
    def __init__(self, meta: dict) -> None:
        self._meta = meta

    def call(self, method, args=(), kwargs=None, *, timeout_s=None):
        if method == "env.get_env_meta":
            return self._meta
        if method == "env.reset":
            return {"robot_state": {}}
        if method == "env.step":
            return [{"robot_state": {}}, 0.0, False, False, {}]
        raise AssertionError(f"unexpected method: {method}")


def test_write_calls_are_marked_before_the_rpc() -> None:
    meta = {"camera_h": 84, "camera_w": 84}
    client = RoboCasaEnvClient(_Rpc(meta), expected_meta=meta)

    with track_execution() as trace:
        client.reset()
        client.step([0.0] * 7)

    assert trace.writes == ["reset", "step"]
