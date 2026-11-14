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


def _component(write_toml, root, name, kind, *, requires=(), imports=()):
    required = ", ".join(f'"{item}"' for item in requires)
    imported = ", ".join(f'"{item}"' for item in imports)
    manifest = write_toml(
        f"{root}/{name}/component.toml",
        f"""
        schema = 1
        name = "{name}"
        kind = "{kind}"
        probe = "{name}"
        requires = [{required}]
        imports = [{imported}]
        """,
    )
    _skeleton(manifest.parent, kind)


#: Files a new component of each kind needs for K2 to pass.
SKELETON = {
    "robot": (
        "__init__.py",
        "spec.py",
        "config.py",
        "adapter.py",
        "prompts/__init__.py",
        "prompts/domain.py",
        "prompts/tools.py",
    ),
    "toolkit": ("__init__.py", "tool.py", "core.py", "observation.py"),
    "capability": ("__init__.py", "server.py", "config.py", "README.md"),
}


def _skeleton(directory, kind):
    for relative in SKELETON[kind]:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    if kind == "toolkit":
        (directory / "evaluation").mkdir(exist_ok=True)


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


def test_relative_cross_robot_import_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "robots", "beta", "robot")
    # ``from .. import beta`` names the sibling package without any absolute
    # module path, so K4 has to resolve the alias to see the boundary crossing.
    _write(tmp_path / "robots" / "alpha" / "module.py", "from .. import beta\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "must not import robot 'beta'" in result.stdout


def test_absolute_alias_cross_robot_import_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "robots", "beta", "robot")
    # ``from robots import beta`` names the sibling package through a bare
    # alias; the absolute branch has to expand it like the relative one.
    _write(tmp_path / "robots" / "alpha" / "module.py", "from robots import beta\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "must not import robot 'beta'" in result.stdout


def test_relative_sibling_capability_import_is_reported(tmp_path, write_toml):
    _component(write_toml, "capabilities", "alpha", "capability")
    _component(write_toml, "capabilities", "beta", "capability")
    _write(
        tmp_path / "capabilities" / "alpha" / "server.py",
        "from ..beta import client\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "capability 'alpha' must not import sibling 'beta'" in result.stdout


def test_relative_toolkit_import_of_a_robot_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "toolkits" / "geometry" / "core.py",
        "from ...robots.alpha import spec\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "toolkits must not import robots" in result.stdout


def test_declared_extension_allows_a_relative_import(tmp_path, write_toml):
    _component(
        write_toml, "robots", "alpha", "robot", requires=["beta"], imports=["beta"]
    )
    _component(write_toml, "robots", "beta", "robot")
    _write(tmp_path / "robots" / "alpha" / "module.py", "from .. import beta\n")

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


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
    _component(
        write_toml, "robots", "alpha", "robot", requires=["beta"], imports=["beta"]
    )
    _component(write_toml, "robots", "beta", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "module.py",
        "from robots.beta import helpers\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_unowned_top_level_entries_are_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    (tmp_path / "scratch").mkdir()
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "top-level directory 'scratch'" in result.stdout
    assert "root file 'notes.txt'" in result.stdout


def test_core_must_not_name_a_concrete_robot(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(
        tmp_path / "rpent" / "planner.py",
        'if robot == "alpha":\n    pass\n',
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core names 'alpha'" in result.stdout


def test_core_uppercase_constant_naming_a_robot_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "rpent" / "env" / "wire.py", "ALPHA_OSC = 1\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core names 'ALPHA'" in result.stdout


def test_slice_entry_must_load_lazily(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "__init__.py",
        "from robots.alpha.spec import get_robot_spec\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "slice __init__.py must stay lazy" in result.stdout


def test_role_file_over_limit_is_a_warning(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "robots" / "alpha" / "spec.py", "x = 1\n" * 81)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout
    assert "warning: spec.py has 81 lines" in result.stdout


def test_new_component_missing_skeleton_files_is_an_error(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    (tmp_path / "robots" / "alpha" / "adapter.py").unlink()

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "robot 'alpha' is missing its skeleton files: adapter.py" in result.stdout


def test_legacy_component_missing_skeleton_files_only_warns(tmp_path, write_toml):
    _component(write_toml, "robots", "libero", "robot")
    (tmp_path / "robots" / "libero" / "adapter.py").unlink()

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout
    assert "robot 'libero' is missing its skeleton files: adapter.py" in result.stdout


def test_new_slice_may_not_add_retired_names(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "robots" / "alpha" / "robot_spec.py", "")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "slice 'alpha' added retired names robot_spec.py" in result.stdout


def test_pre_migration_slice_names_only_warn(tmp_path, write_toml):
    _component(write_toml, "robots", "libero", "robot")
    _write(tmp_path / "robots" / "libero" / "robot_spec.py", "")

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout
    assert "slice 'libero' still has 1 pre-migration names" in result.stdout
    assert "robot_spec.py" in result.stdout


def test_capability_toolkit_and_core_imports_are_rejected(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "capabilities", "sam3", "capability")
    _component(write_toml, "toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "capabilities" / "sam3" / "client.py",
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
