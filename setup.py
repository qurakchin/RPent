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

"""Choose the packages a distribution contains.

A source or editable install includes ``robots/`` and ``components/`` so the
CLI, robot discovery, and component imports work from the checkout. The wheel
published to PyPI sets ``RPENT_WHEEL_SCOPE=core`` and contains only ``rpent/``:
robot and model packages are generic top-level names, and their environments
come from ``installs/targets/``, which ships with the source checkout. The
sdist is built from the source scope and carries every package (see
``MANIFEST.in``), so a source install remains complete.
"""

import os
from pathlib import Path

from setuptools import find_packages, setup

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

_SOURCE_PACKAGES = ["rpent", "rpent.*"]
_COMPONENT_PACKAGES = ["robots", "robots.*", "components", "components.*"]
_EXCLUDED_PACKAGES = ["tests*", "docs*", "examples*", "docker*"]


def _packages() -> list[str]:
    include = list(_SOURCE_PACKAGES)
    if os.environ.get("RPENT_WHEEL_SCOPE") != "core":
        include.extend(_COMPONENT_PACKAGES)
    return find_packages(include=include, exclude=_EXCLUDED_PACKAGES)


def _extras() -> dict[str, list[str]]:
    """Return the compatibility extras, or none for the published core wheel."""
    if os.environ.get("RPENT_WHEEL_SCOPE") == "core":
        return {}
    pyproject = Path(__file__).with_name("pyproject.toml")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return {
        name: list(dependencies)
        for name, dependencies in data.get("tool", {})
        .get("rpent", {})
        .get("extras", {})
        .items()
    }


setup(packages=_packages(), extras_require=_extras())
