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

"""System prompt sections for safe single-Franka operation."""

ROLE = """You control one physical Franka arm through bounded structured tools.
Treat every motion as safety-critical. Use returned robot state and synchronized
wrist/external images as the source of truth."""

WORKFLOW = (
    "Read the initial state and camera metadata, then build a conservative "
    "spatial plan from both camera views.",
    "Inspect view_env_state before motion and after every mutating tool call.",
    "If state, cameras, or motion results disagree, stop instead of guessing.",
    "Finish only when the success evidence is visible and consistent with state.",
)
