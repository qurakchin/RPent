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

"""Global prompt definitions shared by robots."""

from __future__ import annotations

from rpent.prompt.utils import BulletList

OUTPUT = BulletList(
    [
        "Brief reasoning before each tool call (1-2 sentences): observation -> decision.",
        "Don't re-read files already in this session. Don't view_env_state right after a primitive tool already returned the state.",
        "Numerical coords in 3 decimals are enough.",
        "Save artifacts BEFORE calling finish. Stop immediately after writing the audit; do not chat further.",
    ]
)

RESULT_FIELDS = """Every tool result carries `call_ok` and `execution_status`.
`call_ok` only means the call was valid and the framework handled it; it never
means the action succeeded. `execution_status` is `completed`, `partial`,
`not_started`, `rejected`, or `unknown`. `no_execution` appears only when the
call produced no physical action, and `execution_uncertain` appears only when
an interrupted call may have outlived the request and must be verified before
retrying."""

# Only hosts that register the shared ``MotionTools`` family report these
# fields; the bundle adds this section alongside RESULT_FIELDS.
MOTION_RESULT_FIELDS = """Motion results also report `stop_reason`,
`stop_evidence`, and `pose_error`. For motion tools `stop_reason` is `arrived`,
`stalled`, `diverging`, `unsafe_motion`, `planning_rejected`, `max_steps`, or
`episode_over`; `max_steps` means the native step budget is exhausted. Other
tools may report their own `stop_reason` values; judge those by `completed` and
`execution_status`. Judge motion by these fields and a fresh observation, not
by `call_ok`."""

USER = {
    "Task": """
    - suite:   {{suite}}
    - task:    {{task}}
    - seed:    {{seed}}
    - output_dir: {{output_dir}}
    - output:  {{output_dir}}/
      - audit filename:  {{recipe_tag}}.json
    """,
}
