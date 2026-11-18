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

"""The installer resolves one profile, installs its lock, and fingerprints it."""

import os
import shlex
import stat
import sys

import pytest

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import read_fingerprint, runtime_platform
from rpent.install.installer import (
    VENV_DIR,
    default_venv,
    find_uv,
    index_options,
    install,
    profile_resolution,
)
from rpent.install.requirements import (
    REQUIREMENTS_SCHEMA,
    read_core_dependencies,
    requirements_sha256,
)


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
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "json"
        dependencies = ["numpy>=2"]
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "installs/profiles/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"
        lock = "installs/locks/alpha.lock"

        [components.alpha]
        placement = "in-env"
        """,
    )
    write_toml(
        "installs/profiles/beta.toml",
        f"""
        schema = 1
        name = "beta"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"
        core = false

        [components]
        """,
    )
    return tmp_path


def _write_lock(repo, text="numpy==2.0.0\npackaging==24.0\n"):
    lock = repo / "installs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(text, encoding="utf-8")
    return lock


def test_default_venv_is_per_profile(repo):
    profile = discover(repo).profiles["alpha"]

    assert VENV_DIR == ".venvs"
    assert default_venv(repo, profile) == repo / ".venvs" / "alpha"


def test_profile_resolution_selects_the_named_profile(repo):
    catalog = discover(repo)

    resolution = profile_resolution("alpha", catalog, root=repo)

    assert resolution.ok
    assert resolution.profile.name == "alpha"


def test_unknown_profile_lists_known_profiles(repo):
    with pytest.raises(InstallError, match="known profiles: alpha, beta"):
        profile_resolution("missing", discover(repo), root=repo)


def test_find_uv_prefers_override(monkeypatch):
    monkeypatch.setenv("RPENT_UV", "/custom/uv")

    assert find_uv() == "/custom/uv"


def test_index_options_preserve_order(make_profile):
    profile = make_profile(
        "alpha",
        index_url="https://index.test/simple",
        extra_index_urls=("https://extra.test/simple",),
        index_strategy="unsafe-first-match",
    )

    assert index_options(profile) == [
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
    _write_lock(repo)
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"

    fingerprint = install("alpha", root=repo, venv=venv, verbose=False)

    assert read_fingerprint(venv) == fingerprint
    assert fingerprint["schema"] == REQUIREMENTS_SCHEMA
    assert fingerprint["profile"] == "alpha"
    assert fingerprint["components"]["alpha"]["placement"] == "in-env"
    assert fingerprint["component_profiles"]["alpha"] == ["alpha"]
    assert fingerprint["requirements_file"] == ".rpent/requirements/alpha.txt"
    assert fingerprint["source_commit"] is None
    assert os.path.isfile(venv / "bin" / "python")


def test_install_installs_from_the_profile_lock(repo, tmp_path, monkeypatch):
    lock = _write_lock(repo)
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    requirements_arguments = install_arguments()[0]
    assert requirements_arguments[requirements_arguments.index("-r") + 1] == str(lock)
    assert fingerprint["lock"] == "installs/locks/alpha.lock"
    # The lock is an input of the requirements hash `doctor` recomputes, so
    # installing from it does not change the recorded hash.
    resolution = profile_resolution("alpha", discover(repo), root=repo)
    assert fingerprint["requirements_sha256"] == requirements_sha256(
        resolution,
        root=repo,
        core_dependencies=read_core_dependencies(repo),
    )


def test_install_requires_the_profile_lock(repo, tmp_path, monkeypatch):
    _fake_uv(tmp_path, monkeypatch)

    with pytest.raises(
        InstallError,
        match="maintainers regenerate it with `python -m tests.tooling.lock",
    ):
        install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)


def test_install_rejects_a_lock_that_lost_a_requirement(repo, tmp_path, monkeypatch):
    _write_lock(repo, "numpy==2.0.0\n")
    _fake_uv(tmp_path, monkeypatch)

    with pytest.raises(InstallError, match="does not cover 'packaging'"):
        install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)


def test_install_passes_override_files_by_absolute_path(
    repo, tmp_path, write_toml, monkeypatch
):
    # uv resolves relative paths against its working directory, and the CLI may
    # be run from a subdirectory, so manifests are resolved against the
    # checkout before being handed over.
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 1
        name = "alpha"
        kind = "robot"
        probe = "json"
        dependencies = ["numpy>=2"]
        overrides = ["requirements/override.txt"]
        """,
    )
    write_toml("robots/alpha/requirements/override.txt", "numpy<3\n")
    _write_lock(repo)
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    arguments = install_arguments()[0]
    value = arguments[arguments.index("--override") + 1]
    assert value == str(repo / "robots/alpha/requirements/override.txt")
    assert os.path.isabs(value)


def test_install_runs_uv_inside_the_checkout(repo, tmp_path, monkeypatch):
    # uv discovers ``[tool.uv]`` by walking up from its working directory, so
    # installing from a subdirectory must not resolve with other settings.
    _write_lock(repo)
    _fake_uv(tmp_path, monkeypatch)
    monkeypatch.chdir(repo / "robots")

    install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

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
    for name in ("alpha", "beta"):
        write_toml(
            f"robots/{name}/component.toml",
            f"""
            schema = 1
            name = "{name}"
            kind = "robot"
            probe = "json"
            requires = ["shared"]
            """,
        )
    write_toml(
        "installs/deps/shared.toml",
        """
        schema = 1
        name = "shared"
        kind = "deps"
        probe = "json"
        dependencies = ["packaging"]
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "installs/profiles/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"
        core = false

        [components.alpha]
        placement = "in-env"
        """,
    )
    write_toml("installs/locks/alpha.lock", "packaging==24.0\n")
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("alpha", root=tmp_path, venv=tmp_path / "venv", verbose=True)

    assert "probe shared: import json" in capsys.readouterr().out
    assert fingerprint["components"]["shared"]["placement"] == "in-env"


def test_install_refuses_a_venv_belonging_to_another_profile(
    repo, tmp_path, monkeypatch
):
    _write_lock(repo)
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "rpent-install.json").write_text('{"profile": "beta"}\n', encoding="utf-8")

    with pytest.raises(InstallError, match="already installed for profile 'beta'"):
        install("alpha", root=repo, venv=venv, verbose=False)


def test_install_refuses_a_non_empty_venv_without_a_fingerprint(
    repo, tmp_path, monkeypatch
):
    _write_lock(repo)
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "unrelated.txt").write_text("", encoding="utf-8")

    with pytest.raises(InstallError, match="records no installation fingerprint"):
        install("alpha", root=repo, venv=venv, verbose=False)


def test_force_installs_into_a_non_empty_venv(repo, tmp_path, monkeypatch):
    _write_lock(repo)
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "unrelated.txt").write_text("", encoding="utf-8")

    fingerprint = install("alpha", root=repo, venv=venv, force=True, verbose=False)

    assert fingerprint["profile"] == "alpha"


def test_core_profile_installs_the_editable_checkout(repo, tmp_path, monkeypatch):
    _write_lock(repo)
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    editable = install_arguments()[1]
    assert "-e" in editable
    assert "--no-deps" in editable


def test_core_false_profile_skips_the_editable_checkout(
    tmp_path, write_toml, monkeypatch
):
    write_toml(
        "pyproject.toml",
        '[project]\nname = "rpent"\ndependencies = []\n',
    )
    write_toml(
        "installs/profiles/beta.toml",
        f"""
        schema = 1
        name = "beta"
        python = "{sys.version_info.major}.{sys.version_info.minor}"
        platform = "{runtime_platform()}"
        core = false
        dependencies = ["packaging"]
        """,
    )
    write_toml("installs/locks/beta.lock", "packaging==24.0\n")
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    install("beta", root=tmp_path, venv=tmp_path / "venv", verbose=False)

    assert all("-e" not in arguments for arguments in install_arguments())
