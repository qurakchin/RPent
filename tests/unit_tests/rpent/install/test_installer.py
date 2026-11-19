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

"""The installer resolves one target, installs its requirements, and fingerprints it."""

import os
import shlex
import stat
import sys

import pytest

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import read_fingerprint
from rpent.install.installer import (
    VENV_DIR,
    default_venv,
    environment_name,
    find_uv,
    index_options,
    install,
    target_resolution,
)
from rpent.install.requirements import (
    INPUT_SCHEMA,
    read_core_dependencies,
    requirements_sha256,
)
from rpent.install.resolve import resolve


@pytest.fixture
def repo(tmp_path, write_toml):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = ["packaging"]
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "components/models/alpha/component.toml",
        f"""
        schema = 2
        name = "model-alpha"
        probe = "json"
        python = "{major}.{minor}"
        platforms = ["linux-x86_64", "darwin-arm64"]
        dependencies = ["numpy>=2"]
        """,
    )
    write_toml(
        "installs/targets/beta.toml",
        """
        schema = 2
        name = "beta"
        core = false

        [components]
        """,
    )
    return tmp_path


def test_default_venv_is_per_target(repo):
    target = discover(repo).targets["model-alpha"]

    assert VENV_DIR == ".venvs"
    assert default_venv(repo, target.name) == repo / ".venvs" / "model-alpha"


def test_composition_gets_its_own_environment_name():
    assert environment_name("robot-libero") == "robot-libero"
    assert environment_name("robot-libero", ("infra-dev",)) == "robot-libero+infra-dev"


def test_target_resolution_selects_the_named_target(repo):
    catalog = discover(repo)

    resolution = target_resolution("model-alpha", catalog, root=repo)

    assert resolution.ok
    assert resolution.target.name == "model-alpha"


def test_unknown_target_lists_known_targets(repo):
    with pytest.raises(InstallError, match="known targets: beta, model-alpha"):
        target_resolution("missing", discover(repo), root=repo)


def test_with_composes_a_component_into_the_resolution(repo, write_toml):
    write_toml(
        "components/infra/test_tools/component.toml",
        """
        schema = 2
        name = "infra-test_tools"
        probe = "json"
        platforms = ["linux-x86_64", "darwin-arm64"]
        dependencies = ["pytest"]
        """,
    )

    resolution = target_resolution(
        "model-alpha",
        discover(repo),
        root=repo,
        extra_components=("infra-test_tools",),
    )

    assert resolution.ok
    assert "infra-test_tools" in resolution.components
    assert "model-alpha" in resolution.components


def test_with_rejects_an_unknown_component(repo):
    with pytest.raises(InstallError, match="unknown component\\(s\\) for --with"):
        target_resolution(
            "model-alpha",
            discover(repo),
            root=repo,
            extra_components=("infra-missing",),
        )


def test_find_uv_prefers_override(monkeypatch):
    monkeypatch.setenv("RPENT_UV", "/custom/uv")

    assert find_uv() == "/custom/uv"


def test_index_options_preserve_order(make_target, make_catalog):
    target = make_target(
        "alpha",
        index_url="https://index.test/simple",
        extra_index_urls=("https://extra.test/simple",),
        index_strategy="unsafe-first-match",
    )
    resolution = resolve(target, make_catalog(components=[]))

    assert index_options(resolution) == [
        "--index-url",
        "https://index.test/simple",
        "--extra-index-url",
        "https://extra.test/simple",
        "--index-strategy",
        "unsafe-first-match",
    ]


def _fake_uv(tmp_path, monkeypatch):
    """Create a uv stand-in and return it with a reader for install arguments."""
    uv = tmp_path / "uv"
    uv.write_text(
        f"""#!/bin/sh
set -eu
pwd -P >> "$(dirname "$0")/uv-pwd"
if [ "$1" = "venv" ]; then
  for last; do :; done
  mkdir -p "$last/bin"
  printf '#!/bin/sh\\nexec {shlex.quote(sys.executable)} "$@"\\n' > "$last/bin/python"
  chmod +x "$last/bin/python"
elif [ "$1 $2" = "pip install" ]; then
  {{ printf '%s\\n' "$@"; echo --; }} >> "$(dirname "$0")/uv-install-args"
elif [ "$1 $2" = "pip freeze" ]; then
  echo "alpha==1.0.0"
fi
exit 0
""",
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("RPENT_UV", str(uv))

    def install_arguments():
        """Return each ``uv pip install`` invocation's arguments."""
        text = (tmp_path / "uv-install-args").read_text(encoding="utf-8")
        return [block.splitlines() for block in text.split("--\n") if block.strip()]

    return uv, install_arguments


def _uv_working_directories(tmp_path):
    """Return the directory each ``uv`` invocation of the fake ran in."""
    return (tmp_path / "uv-pwd").read_text(encoding="utf-8").splitlines()


def test_install_records_a_fingerprint_with_a_fake_uv(repo, tmp_path, monkeypatch):
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"

    fingerprint = install("model-alpha", root=repo, venv=venv, verbose=False)

    assert read_fingerprint(venv) == fingerprint
    assert fingerprint["schema"] == INPUT_SCHEMA
    assert fingerprint["target"] == "model-alpha"
    assert "model-alpha" in fingerprint["components"]
    assert fingerprint["requirements_file"] == "rpent-requirements.txt"
    assert "component_targets" not in fingerprint
    assert "lock" not in fingerprint
    assert fingerprint["source_commit"] is None
    assert os.path.isfile(venv / "bin" / "python")


def test_install_records_with_components_in_the_fingerprint(
    repo, tmp_path, write_toml, monkeypatch
):
    write_toml(
        "components/infra/test_tools/component.toml",
        """
        schema = 2
        name = "infra-test_tools"
        probe = "json"
        platforms = ["linux-x86_64", "darwin-arm64"]
        dependencies = ["pytest"]
        """,
    )
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install(
        "model-alpha",
        root=repo,
        venv=tmp_path / "venv",
        verbose=False,
        extra_components=("infra-test_tools",),
    )

    assert fingerprint["with"] == ["infra-test_tools"]
    assert "infra-test_tools" in fingerprint["components"]
    requirements = (tmp_path / "venv" / "rpent-requirements.txt").read_text(
        encoding="utf-8"
    )
    assert "pytest" in requirements


def test_install_installs_from_the_rendered_requirements(repo, tmp_path, monkeypatch):
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("model-alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    requirements = tmp_path / "venv" / "rpent-requirements.txt"
    requirements_arguments = install_arguments()[0]
    assert requirements_arguments[requirements_arguments.index("-r") + 1] == str(
        requirements
    )
    text = requirements.read_text(encoding="utf-8")
    assert "numpy>=2" in text
    resolution = target_resolution("model-alpha", discover(repo), root=repo)
    assert fingerprint["requirements_sha256"] == requirements_sha256(
        resolution,
        root=repo,
        core_dependencies=read_core_dependencies(repo),
    )


def test_install_does_not_read_a_checked_in_lock(repo, tmp_path, monkeypatch):
    # A lock is a reproduction artifact. A stale or missing one must neither
    # change the installed requirements nor fail the install.
    stale = repo / "tests" / "locks" / "model-alpha.lock"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("numpy==0.1\n", encoding="utf-8")
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("model-alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    arguments = install_arguments()[0]
    assert arguments[arguments.index("-r") + 1] == str(
        tmp_path / "venv" / "rpent-requirements.txt"
    )
    assert str(stale) not in arguments


def test_install_passes_override_files_by_absolute_path(
    repo, tmp_path, write_toml, monkeypatch
):
    # uv resolves relative paths against its working directory, and the CLI may
    # be run from a subdirectory, so manifests are resolved against the
    # checkout before being handed over.
    write_toml(
        "components/models/alpha/component.toml",
        """
        schema = 2
        name = "model-alpha"
        probe = "json"
        python = "3.11"
        platforms = ["linux-x86_64", "darwin-arm64"]
        dependencies = ["numpy>=2"]
        overrides = ["requirements/override.txt"]
        """,
    )
    write_toml("components/models/alpha/requirements/override.txt", "numpy<3\n")
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("model-alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    arguments = install_arguments()[0]
    value = arguments[arguments.index("--override") + 1]
    assert value == str(repo / "components/models/alpha/requirements/override.txt")
    assert os.path.isabs(value)


def test_install_runs_uv_inside_the_checkout(repo, tmp_path, monkeypatch):
    # uv discovers ``[tool.uv]`` by walking up from its working directory, so
    # installing from a subdirectory must not resolve with other settings.
    _fake_uv(tmp_path, monkeypatch)
    monkeypatch.chdir(repo / "components")

    install("model-alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    assert set(_uv_working_directories(tmp_path)) == {str(repo.resolve())}


def test_install_probes_the_deps_components_of_the_environment(
    tmp_path, write_toml, monkeypatch, capsys
):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    major, minor = sys.version_info[:2]
    for name in ("alpha", "beta"):
        write_toml(
            f"components/models/{name}/component.toml",
            f"""
            schema = 2
            name = "model-{name}"
            probe = "json"
            python = "{major}.{minor}"
            platforms = ["linux-x86_64", "darwin-arm64"]
            requires = ["infra-shared"]
            """,
        )
    write_toml(
        "components/infra/shared/component.toml",
        """
        schema = 2
        name = "infra-shared"
        probe = "json"
        platforms = ["linux-x86_64", "darwin-arm64"]
        dependencies = ["packaging"]
        """,
    )
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("model-alpha", root=tmp_path, venv=tmp_path / "venv", verbose=True)

    assert "probe infra-shared: import json" in capsys.readouterr().out
    assert "infra-shared" in fingerprint["components"]


def test_install_refuses_a_venv_belonging_to_another_target(
    repo, tmp_path, monkeypatch
):
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "rpent-install.json").write_text('{"target": "beta"}\n', encoding="utf-8")

    with pytest.raises(InstallError, match="already installed for target 'beta'"):
        install("model-alpha", root=repo, venv=venv, verbose=False)


def test_install_refuses_a_non_empty_venv_without_a_fingerprint(
    repo, tmp_path, monkeypatch
):
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "unrelated.txt").write_text("", encoding="utf-8")

    with pytest.raises(InstallError, match="records no installation fingerprint"):
        install("model-alpha", root=repo, venv=venv, verbose=False)


def test_force_installs_into_a_non_empty_venv(repo, tmp_path, monkeypatch):
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "unrelated.txt").write_text("", encoding="utf-8")

    fingerprint = install("model-alpha", root=repo, venv=venv, force=True, verbose=False)

    assert fingerprint["target"] == "model-alpha"


def test_core_target_installs_the_editable_checkout(repo, tmp_path, monkeypatch):
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("model-alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    editable = install_arguments()[1]
    assert "-e" in editable
    assert "--no-deps" in editable


def test_core_false_target_skips_the_editable_checkout(
    tmp_path, write_toml, monkeypatch
):
    write_toml(
        "pyproject.toml",
        '[project]\nname = "rpent"\ndependencies = []\n',
    )
    write_toml(
        "installs/targets/beta.toml",
        """
        schema = 2
        name = "beta"
        core = false
        dependencies = ["packaging"]
        """,
    )
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("beta", root=tmp_path, venv=tmp_path / "venv", verbose=False)

    assert all("-e" not in arguments for arguments in install_arguments())


def test_dry_run_prints_the_requirements_and_creates_nothing(
    repo, tmp_path, monkeypatch, capsys
):
    uv, _ = _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"

    fingerprint = install("model-alpha", root=repo, venv=venv, verbose=False, dry_run=True)

    printed = capsys.readouterr().out
    assert fingerprint == {}
    assert "# target model-alpha:" in printed
    assert "numpy>=2" in printed
    assert not venv.exists()
    assert not (venv / "rpent-requirements.txt").exists()
    assert not (repo / ".rpent").exists()
    assert not (tmp_path / "uv-install-args").exists()
