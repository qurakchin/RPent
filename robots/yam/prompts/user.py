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

"""User prompt for one YAM run."""

CELL = """- task: {{task_name}}
- seed label: {{seed}}
- instruction: {{instruction}}
"""

BEGIN = """Follow the required read order, bind the current target and relation
from fresh YAM observations, then execute the first unmet phase. Use the complete
task language as the overall goal.
Verify env eval_success before finish."""
