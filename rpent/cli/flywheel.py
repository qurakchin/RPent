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

"""Entry point for the ``rpent-flywheel`` console script.

The exporter is the ``tool-flywheel`` component, which no core module needs at
import time. The import stays inside :func:`main` so a core-only wheel keeps a
working ``--help`` and reports a missing component instead of failing to load.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def main(argv: list[str] | None = None) -> int:
    """Run the flywheel exporter installed in this environment."""
    try:
        from components.tools.flywheel import cli
    except ImportError as exc:
        print(
            "rpent-flywheel is the tool-flywheel component; install it with "
            "`rpent-install install tool-flywheel` in this environment",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main())
