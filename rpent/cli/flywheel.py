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

"""``rpent-flywheel`` entry point.

The implementation ships as the ``tool-flywheel`` component, so the console
script exists in every environment while the import happens on use. An
environment without the component reports how to add it instead of failing
with a bare ``ModuleNotFoundError``.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Run the flywheel CLI, or explain which component installs it."""
    try:
        from components.tools.flywheel.cli import main as run
    except ModuleNotFoundError as exc:
        if exc.name != "components.tools.flywheel" and not (
            exc.name or ""
        ).startswith("components.tools.flywheel."):
            raise
        print(
            "rpent-flywheel needs the tool-flywheel component: install a "
            "target that selects it, for example `rpent-install install "
            "unit-cpu`, or add [components.tool-flywheel] to your target.",
            file=sys.stderr,
        )
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
