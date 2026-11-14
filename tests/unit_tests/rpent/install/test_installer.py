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

"""The installer resolves targets, renders requirements, and records fingerprints."""

import os
import shlex
import stat
import sys

import pytest

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.fingerprint import read_fingerprint, runtime_platform
from rpent.install.installer import (
    _with_dev,
    find_uv,
    index_options,
    install,
    resolve_install_target,
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
    write_toml(
        "robots/beta/component.toml",
        """
        schema = 1
        name = "beta"
        kind = "robot"
        probe = "json"
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "envs/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"
        lock = "envs/locks/alpha.lock"

        [components.alpha]
        placement = "in-env"
        """,
    )
    write_toml(
        "envs/dev.toml",
        f"""
        schema = 1
        name = "dev"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"
        extra = "test"
        dependencies = ["pytest"]

        [components]
        """,
    )
    return tmp_path


def test_dry_run_renders_requirements_without_uv(repo, monkeypatch, capsys):
    monkeypatch.delenv("RPENT_UV", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    result = install("alpha", root=repo, dry_run=True, verbose=False)

    assert result["profile"] == "alpha"
    assert result["external_environments"] == []
    assert "packaging" in result["requirements"]
    assert "numpy>=2" in result["requirements"]
    assert "packaging" in capsys.readouterr().out


def test_resolve_install_target_adds_dev_profile(repo):
    catalog = discover(repo)

    resolution = resolve_install_target("alpha", catalog, root=repo, include_dev=True)

    assert resolution.ok
    assert "dev" not in resolution.components
    assert "pytest" in resolution.profile.dependencies

    with pytest.raises(InstallError, match="--dev applies to profiles"):
        resolve_install_target("beta", catalog, root=repo, include_dev=True)


def test_with_dev_is_idempotent(repo):
    catalog = discover(repo)
    profile = catalog.profiles["alpha"]

    once = _with_dev(profile, catalog)
    twice = _with_dev(once, catalog)

    assert once.dependencies == ("pytest",)
    assert twice.dependencies == once.dependencies


def test_component_target_uses_running_interpreter(repo):
    catalog = discover(repo)

    resolution = resolve_install_target("beta", catalog, root=repo)

    profile = resolution.profile
    assert profile.name == "beta"
    assert profile.python == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert profile.platform == runtime_platform()


def test_unknown_target_lists_known_profiles(repo):
    with pytest.raises(InstallError, match="known profiles: alpha, dev"):
        resolve_install_target("missing", discover(repo), root=repo)


def test_component_target_selects_its_variant_explicitly(tmp_path, write_toml):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    write_toml(
        "robots/gamma/component.toml",
        """
        schema = 1
        name = "gamma"
        kind = "robot"
        probe = "json"
        variant_required = true

        [optional]
        pro = ["numpy"]
        lite = ["packaging"]
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "envs/gamma-pro.toml",
        f"""
        schema = 1
        name = "gamma-pro"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"

        [components.gamma]
        variant = "pro"
        """,
    )
    catalog = discover(tmp_path)

    with pytest.raises(InstallError) as error:
        resolve_install_target("gamma", catalog, root=tmp_path)
    message = str(error.value)
    assert "requires a variant" in message
    assert "--variant <lite|pro>" in message
    assert "gamma-pro" in message

    with pytest.raises(InstallError, match="has no optional group 'nope'"):
        resolve_install_target("gamma", catalog, root=tmp_path, variant="nope")

    resolution = resolve_install_target("gamma", catalog, root=tmp_path, variant="pro")

    assert resolution.ok
    assert resolution.profile.synthetic
    assert resolution.profile.components["gamma"].variant == "pro"


def test_component_target_rejects_a_variant_for_a_profile(repo):
    with pytest.raises(InstallError, match="--variant applies only to a single"):
        resolve_install_target("alpha", discover(repo), root=repo, variant="pro")


def test_component_target_reports_profiles_that_place_it(tmp_path, write_toml):
    write_toml(
        "pyproject.toml",
        """
        [project]
        name = "rpent"
        dependencies = []
        """,
    )
    write_toml(
        "capabilities/delta/component.toml",
        """
        schema = 1
        name = "delta"
        kind = "capability"
        probe = "json"
        placement = ["remote"]
        """,
    )
    major, minor = sys.version_info[:2]
    write_toml(
        "envs/delta-remote.toml",
        f"""
        schema = 1
        name = "delta-remote"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"

        [components.delta]
        placement = "remote"
        """,
    )
    catalog = discover(tmp_path)

    with pytest.raises(InstallError) as error:
        resolve_install_target("delta", catalog, root=tmp_path)

    message = str(error.value)
    assert "no in-env placement" in message
    assert "delta-remote" in message


def test_find_uv_prefers_override(monkeypatch):
    monkeypatch.setenv("RPENT_UV", "/custom/uv")

    assert find_uv() == "/custom/uv"


def test_index_options_preserve_order(make_profile):
    profile = make_profile(
        "alpha",
        index_url="https://index.test/simple",
        extra_index_urls=("https://extra.test/simple",),
    )

    assert index_options(profile) == [
        "--index-url",
        "https://index.test/simple",
        "--extra-index-url",
        "https://extra.test/simple",
    ]


def _fake_uv(tmp_path, monkeypatch):
    """Create a uv stand-in and return it with a reader for install arguments."""
    uv = tmp_path / "uv"
    uv.write_text(
        f"""#!/bin/sh
set -eu
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
        "envs/deps/shared.toml",
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
        "envs/alpha.toml",
        f"""
        schema = 1
        name = "alpha"
        python = "{major}.{minor}"
        platform = "{runtime_platform()}"

        [components.alpha]
        placement = "in-env"
        """,
    )
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("alpha", root=tmp_path, venv=tmp_path / "venv", verbose=True)

    assert "probe shared: import json" in capsys.readouterr().out
    assert fingerprint["components"]["shared"]["placement"] == "in-env"


def test_install_records_a_fingerprint_with_a_fake_uv(repo, tmp_path, monkeypatch):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"

    fingerprint = install("alpha", root=repo, venv=venv, verbose=False)

    assert read_fingerprint(venv) == fingerprint
    assert fingerprint["profile"] == "alpha"
    assert fingerprint["components"]["alpha"]["placement"] == "in-env"
    assert fingerprint["requirements_file"] == ".rpent/envs/alpha.txt"
    assert fingerprint["source_commit"] is None
    assert os.path.isfile(venv / "bin" / "python")


def test_install_uses_the_profile_lock_when_it_exists(repo, tmp_path, monkeypatch):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    requirements_arguments = install_arguments()[0]
    assert requirements_arguments[requirements_arguments.index("-r") + 1] == str(lock)
    assert fingerprint["lock"] == "envs/locks/alpha.lock"


def test_install_rejects_a_lock_that_lost_a_requirement(repo, tmp_path, monkeypatch):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    _fake_uv(tmp_path, monkeypatch)

    with pytest.raises(InstallError, match="does not cover 'packaging'"):
        install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)


def test_install_rejects_a_missing_declared_lock(repo, tmp_path, monkeypatch):
    _fake_uv(tmp_path, monkeypatch)

    with pytest.raises(InstallError, match="does not exist"):
        install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)


def test_install_refuses_a_venv_belonging_to_another_profile(
    repo, tmp_path, monkeypatch
):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "rpent-install.json").write_text('{"profile": "beta"}\n', encoding="utf-8")

    with pytest.raises(InstallError, match="already installed for profile 'beta'"):
        install("alpha", root=repo, venv=venv, verbose=False)


def test_component_install_marks_its_fingerprint(repo, tmp_path, monkeypatch):
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("beta", root=repo, venv=tmp_path / "venv", verbose=False)

    assert fingerprint["install_kind"] == "component"
    assert fingerprint["component"] == "beta"
    assert fingerprint["profile"] is None
    assert fingerprint["reproducible"] is False


def test_profile_install_is_reproducible_when_it_uses_the_lock(
    repo, tmp_path, monkeypatch
):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _fake_uv(tmp_path, monkeypatch)

    fingerprint = install("alpha", root=repo, venv=tmp_path / "venv", verbose=False)

    assert fingerprint["install_kind"] == "profile"
    assert fingerprint["profile"] == "alpha"
    assert fingerprint["component"] is None
    assert fingerprint["reproducible"] is True


def test_component_install_refuses_a_profile_venv(repo, tmp_path, monkeypatch):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _fake_uv(tmp_path, monkeypatch)
    venv = tmp_path / "venv"

    install("beta", root=repo, venv=venv, verbose=False)

    with pytest.raises(InstallError, match="already installed for component 'beta'"):
        install("alpha", root=repo, venv=venv, verbose=False)


def test_install_with_dev_resolves_instead_of_using_the_lock(
    repo, tmp_path, monkeypatch
):
    lock = repo / "envs/locks/alpha.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("numpy==2.0.0\npackaging==24.0\n", encoding="utf-8")
    _, install_arguments = _fake_uv(tmp_path, monkeypatch)

    fingerprint = install(
        "alpha", root=repo, venv=tmp_path / "venv", include_dev=True, verbose=False
    )

    requirements_arguments = install_arguments()[0]
    assert requirements_arguments[requirements_arguments.index("-r") + 1] == str(
        repo / ".rpent/envs/alpha.txt"
    )
    assert fingerprint["lock"] is None
