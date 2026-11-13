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

"""Layout checks reject imports across component ownership boundaries."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_layout.py"


def _component(write_toml, root, name, kind, *, requires=()):
    rendered = ", ".join(f'"{item}"' for item in requires)
    write_toml(
        f"{root}/{name}/component.toml",
        f"""
        schema = 1
        name = "{name}"
        kind = "{kind}"
        probe = "{name}"
        requires = [{rendered}]
        """,
    )


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(root):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_missing_component_manifest_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    (tmp_path / "toolkits" / "geometry").mkdir(parents=True)

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "toolkit directory has no component.toml" in result.stdout


def test_cross_robot_import_requires_a_declared_extension(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "robots", "beta", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "module.py",
        "from robots.beta import helpers\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "must not import robot 'beta'" in result.stdout


def test_apple_double_python_files_are_ignored(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "robots", "beta", "robot")
    _write(tmp_path / "robots" / "alpha" / "module.py", "import json\n")
    # Network filesystems store macOS extended attributes as ._<name> files.
    (tmp_path / "robots" / "alpha" / "._module.py").write_bytes(
        b"\xa3\nfrom robots.beta import helpers\n"
    )

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_declared_coinstalled_extension_allows_cross_robot_import(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot", requires=["beta"])
    _component(write_toml, "robots", "beta", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "module.py",
        "from robots.beta import helpers\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_capability_toolkit_and_core_imports_are_rejected(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "rpent/robots/components", "sam3", "capability")
    _component(write_toml, "toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "rpent" / "robots" / "components" / "sam3" / "client.py",
        "from robots.alpha import robot_spec\n",
    )
    _write(
        tmp_path / "toolkits" / "geometry" / "tool.py",
        "import robots\n",
    )
    _write(
        tmp_path / "rpent" / "planner" / "planner.py",
        "from robots.alpha import robot_spec\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "capability 'sam3' must not import robots" in result.stdout
    assert "toolkits must not import robots" in result.stdout
    assert "core must not import concrete robot 'alpha'" in result.stdout
