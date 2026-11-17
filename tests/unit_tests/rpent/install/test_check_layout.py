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
from datetime import date
from pathlib import Path

from rpent.install import layout

REPO_ROOT = Path(__file__).resolve().parents[4]

#: Package groups each component root lives under; all must stay importable.
GROUP_INITS = {
    "robots": ("robots",),
    "components/models": ("components", "components/models"),
    "components/toolkits": ("components", "components/toolkits"),
}


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
    # ``manifest.parents[0]`` is the component directory, so the synthetic
    # repository root sits one level above its root directory.
    base = manifest.parents[len(Path(root).parts) + 1]
    for relative in GROUP_INITS[root]:
        directory = base / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").touch()


#: Files a new component of each kind needs for K2 to pass.
SKELETON = {
    "robot": (
        "__init__.py",
        "spec.py",
        "config.py",
        "adapter.py",
        "prompts/__init__.py",
        "prompts/domain.py",
    ),
    "toolkit": ("__init__.py", "tool.py", "core.py", "observation.py"),
    "model": ("__init__.py", "server.py"),
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
        [sys.executable, "-m", "rpent.install.layout", "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_missing_component_manifest_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    (tmp_path / "components" / "toolkits" / "geometry").mkdir(parents=True)

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


def test_relative_sibling_model_import_is_reported(tmp_path, write_toml):
    _component(write_toml, "components/models", "alpha", "model")
    _component(write_toml, "components/models", "beta", "model")
    _write(
        tmp_path / "components" / "models" / "alpha" / "server.py",
        "from ..beta import client\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "model 'alpha' must not import sibling 'beta'" in result.stdout


def test_relative_toolkit_import_of_a_robot_is_reported(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "components/toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "components" / "toolkits" / "geometry" / "core.py",
        "from ....robots.alpha import spec\n",
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


def test_model_toolkit_and_core_imports_are_rejected(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _component(write_toml, "components/models", "sam3", "model")
    _component(write_toml, "components/toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "components" / "models" / "sam3" / "client.py",
        "from robots.alpha import robot_spec\n",
    )
    _write(
        tmp_path / "components" / "toolkits" / "geometry" / "tool.py",
        "import robots\n",
    )
    _write(
        tmp_path / "rpent" / "planner" / "planner.py",
        "from robots.alpha import robot_spec\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "model 'sam3' must not import robots" in result.stdout
    assert "toolkits must not import robots" in result.stdout
    assert "core must not import concrete robot 'alpha'" in result.stdout


def test_bare_alias_is_reported_once(tmp_path, write_toml):
    # ``from components.models.sam3 import server`` reaches the same rule through
    # the module path and the expanded alias; it is one violation, not two.
    _component(write_toml, "components/models", "sam3", "model")
    _write(
        tmp_path / "rpent" / "planner" / "planner.py",
        "from components.models.sam3 import server\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert result.stdout.count("core must not import model services") == 1


def test_models_and_toolkits_must_not_import_each_other(tmp_path, write_toml):
    _component(write_toml, "components/models", "sam3", "model")
    _component(write_toml, "components/toolkits", "geometry", "toolkit")
    _write(
        tmp_path / "components" / "models" / "sam3" / "client.py",
        "from components.toolkits.geometry import tool\n",
    )
    _write(
        tmp_path / "components" / "toolkits" / "geometry" / "tool.py",
        "from components.models.sam3 import client\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "model 'sam3' must not import components.toolkits" in result.stdout
    assert "toolkit 'geometry' must not import components.models" in result.stdout


def test_model_contracts_may_name_robots(tmp_path, write_toml):
    # Model-side wire contracts and the backend table name the embodiment they
    # speak to; only scheduling code in the rest of rpent/ is checked.
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "rpent" / "models" / "platforms.py", 'ALPHA_OSC = "alpha"\n')

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_group_package_keeps_an_empty_group_importable(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    (tmp_path / "robots" / "__init__.py").unlink()

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "package group robots/ needs __init__.py" in result.stdout


def test_model_service_needs_only_its_package_and_server(tmp_path, write_toml):
    # ``config.py`` and ``README.md`` are conventions for a model service, not
    # part of the skeleton a new integration must create.
    _component(write_toml, "components/models", "delta", "model")

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_new_model_without_a_server_is_an_error(tmp_path, write_toml):
    _component(write_toml, "components/models", "delta", "model")
    (tmp_path / "components" / "models" / "delta" / "server.py").unlink()

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "model 'delta' is missing its skeleton files: server.py" in result.stdout


def test_pure_data_module_rejects_runtime_imports(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "observation.py",
        "import torch\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "pure-data module imports third-party 'torch'" in result.stdout


def test_package_entry_point_must_not_import_a_runtime(tmp_path, write_toml):
    _component(write_toml, "components/models", "delta", "model")
    _write(
        tmp_path / "components" / "models" / "delta" / "__init__.py",
        "import torch\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "package entry point imports third-party 'torch'" in result.stdout


def test_pure_data_module_accepts_numpy_and_core_contracts(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(
        tmp_path / "robots" / "alpha" / "observation.py",
        "import numpy\nfrom typing_extensions import TypedDict\n"
        "from rpent.env import observation\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "layout ok" in result.stdout


def test_core_name_exemption_warns_while_it_applies(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "rpent" / "models" / "platforms.py", 'ALPHA_OSC = "alpha"\n')

    findings = layout.check_core_robot_names(tmp_path, today=date(2026, 11, 16))

    assert [finding for finding in findings if finding.level == layout.ERROR] == []
    warnings = [finding.message for finding in findings]
    assert any(
        "K5 exemption for rpent/models applies until 2027-06-30" in message
        for message in warnings
    )


def test_core_name_exemption_fails_once_it_expires(tmp_path, write_toml):
    _component(write_toml, "robots", "alpha", "robot")
    _write(tmp_path / "rpent" / "models" / "platforms.py", 'ALPHA_OSC = "alpha"\n')

    findings = layout.check_core_robot_names(tmp_path, today=date(2030, 1, 1))

    errors = [finding.message for finding in findings if finding.level == layout.ERROR]
    assert any(
        "exemption for 'rpent/models' expired on 2027-06-30" in m for m in errors
    )
    assert any("core names 'ALPHA'" in message for message in errors)


def test_legacy_slice_names_fail_after_the_migration_deadline(tmp_path, write_toml):
    _component(write_toml, "robots", "libero", "robot")
    _write(tmp_path / "robots" / "libero" / "robot_spec.py", "")

    findings = layout.check_legacy_names(tmp_path, today=date(2030, 1, 1))

    assert len(findings) == 1
    assert findings[0].level == layout.ERROR
    assert "has passed" in findings[0].message


def test_legacy_component_skeleton_fails_after_the_migration_deadline(
    tmp_path, write_toml
):
    _component(write_toml, "robots", "libero", "robot")
    (tmp_path / "robots" / "libero" / "adapter.py").unlink()

    findings = layout.check_role_files(tmp_path, today=date(2030, 1, 1))

    assert len(findings) == 1
    assert findings[0].level == layout.ERROR
    assert "migration deadline 2027-06-30 passed" in findings[0].message
