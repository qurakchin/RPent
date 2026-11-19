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

"""Shared component-side contracts.

``env/`` holds the environment RPC client and facade, and ``models/`` the model
contracts, clients, facades and backends. Neither package is an installable
component: robots, simulators and model services import them, and they depend
on no concrete component. Concrete components live in the top-level
``components/`` package, one installable directory per service.
"""
