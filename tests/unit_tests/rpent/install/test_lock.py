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

"""One resolver compiles target locks, records their cutoff, and resolves."""

import os
import stat

import pytest

from rpent.install.discovery import discover
from rpent.install.errors import InstallError
from rpent.install.lock import (
    LOCK_PYTHON_PREFIX,
    LOCK_TIMESTAMP_PREFIX,
    compile_target,
    lock_path,
    lock_python,
    lock_timestamp,
    new_lock_timestamp,
    resolve_target,
)
from rpent.install.manifest import Selection


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
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "json"
        python = "3.11"
        dependencies = ["numpy>=2"]
        """,
    )
    write_toml(
        "robots/beta/component.toml",
        """
        schema = 2
        name = "beta"
        kind = "robot"
        probe = "json"
        python = "3.11"
        manylinux = "2_35"
        """,
    )
    return tmp_path


@pytest.fixture
def fake_uv(tmp_path, monkeypatch):
    """A uv stand-in that records the compiled requirements at --output-file."""
    uv = tmp_path / "uv"
    uv.write_text(
        """#!/bin/sh
set -eu
pwd -P >> "$(dirname "$0")/uv-pwd"
printf '%s\\n' "$@" > "$(dirname "$0")/uv-args"
[ "$1 $2" = "pip compile" ]
source=$3
output=
previous=
for argument in "$@"; do
  if [ "$previous" = "--output-file" ]; then
    output=$argument
  fi
  previous=$argument
done
[ -n "$output" ]
cp "$source" "$output"
""",
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("RPENT_UV", str(uv))
    return uv


def _arguments(fake_uv):
    return (fake_uv.parent / "uv-args").read_text(encoding="utf-8").splitlines()


def test_lock_path_follows_the_target_name(make_target, tmp_path):
    # Locks are optional reproduction artifacts named after their target, so no
    # manifest can point at a different path for the same target.
    assert lock_path(tmp_path, make_target("alpha")) == (
        tmp_path / "tests/locks/alpha.lock"
    )


def test_new_lock_timestamp_is_a_utc_cutoff():
    value = new_lock_timestamp()

    assert value.endswith("Z")
    assert lock_timestamp(f"{LOCK_TIMESTAMP_PREFIX}{value}\npackaging==24.0\n") == value


def test_lock_timestamp_rejects_a_missing_or_naive_header():
    assert lock_timestamp("packaging==24.0\n") is None
    assert lock_timestamp(f"{LOCK_TIMESTAMP_PREFIX}2026-11-16T00:00:00\n") is None
    assert lock_timestamp(f"{LOCK_TIMESTAMP_PREFIX}not-a-date\n") is None


def test_compile_writes_the_resolved_requirements(repo, fake_uv):
    catalog = discover(repo)
    output = repo / "tests/locks/alpha.lock"
    output.parent.mkdir(parents=True, exist_ok=True)
    cutoff = new_lock_timestamp()

    text = compile_target(
        catalog.targets["alpha"],
        catalog,
        root=repo,
        uv=str(fake_uv),
        output=output,
        exclude_newer=cutoff,
    )

    assert "packaging" in text
    assert "numpy>=2" in text
    assert text.startswith(f"{LOCK_PYTHON_PREFIX}3.11\n")
    assert lock_python(text) == "3.11"
    assert lock_timestamp(text) == cutoff
    assert output.read_text(encoding="utf-8") == text
    arguments = _arguments(fake_uv)
    assert arguments[arguments.index("--exclude-newer") + 1] == cutoff


def test_compile_without_a_cutoff_writes_only_the_python_header(repo, fake_uv):
    catalog = discover(repo)
    output = repo / "tests/locks/alpha.lock"
    output.parent.mkdir(parents=True, exist_ok=True)

    text = compile_target(
        catalog.targets["alpha"],
        catalog,
        root=repo,
        uv=str(fake_uv),
        output=output,
    )

    assert text.startswith(LOCK_PYTHON_PREFIX)
    assert LOCK_TIMESTAMP_PREFIX not in text
    assert "--exclude-newer" not in _arguments(fake_uv)


def test_compile_runs_in_the_checkout(repo, fake_uv, monkeypatch):
    # uv discovers ``[tool.uv]`` from its working directory, so a lock compiled
    # from a subdirectory would record versions the checkout does not select.
    monkeypatch.chdir(repo / "robots")
    catalog = discover(repo)
    output = repo / "tests/locks/alpha.lock"
    output.parent.mkdir(parents=True, exist_ok=True)

    compile_target(
        catalog.targets["alpha"], catalog, root=repo, uv=str(fake_uv), output=output
    )

    assert (repo / "uv-pwd").read_text(encoding="utf-8").splitlines() == [
        str(repo.resolve())
    ]


def test_compile_resolves_override_files_against_the_checkout(
    repo, fake_uv, write_toml
):
    # uv resolves relative paths against its working directory, so a compile
    # from a subdirectory would otherwise miss the override.
    write_toml(
        "robots/alpha/component.toml",
        """
        schema = 2
        name = "alpha"
        kind = "robot"
        probe = "json"
        python = "3.11"
        dependencies = ["numpy>=2"]
        overrides = ["requirements/override.txt"]
        """,
    )
    write_toml("robots/alpha/requirements/override.txt", "numpy<3\n")
    catalog = discover(repo)
    output = repo / "tests/locks/alpha.lock"
    output.parent.mkdir(parents=True, exist_ok=True)

    compile_target(
        catalog.targets["alpha"], catalog, root=repo, uv=str(fake_uv), output=output
    )

    arguments = _arguments(fake_uv)
    value = arguments[arguments.index("--overrides") + 1]
    assert value == str(repo / "robots/alpha/requirements/override.txt")
    assert os.path.isabs(value)


def test_compile_uses_the_target_manylinux_baseline(repo, fake_uv):
    catalog = discover(repo)
    output = repo / "tests/locks/beta.lock"
    output.parent.mkdir(parents=True, exist_ok=True)

    compile_target(
        catalog.targets["beta"], catalog, root=repo, uv=str(fake_uv), output=output
    )

    arguments = _arguments(fake_uv)
    assert arguments[arguments.index("--python-platform") + 1] == (
        "x86_64-manylinux_2_35"
    )


def test_compile_rejects_a_python_request_no_supported_minor_satisfies(
    tmp_path, make_component, make_target, make_catalog, fake_uv
):
    component = make_component("alpha", python=">=3.10,<3.11")
    target = make_target(
        "alpha",
        components={"alpha": Selection(placement="in-env")},
        python="3.12",
        core=False,
    )
    catalog = make_catalog([component], {"alpha": target})

    with pytest.raises(InstallError, match="no supported version"):
        compile_target(
            target, catalog, root=tmp_path, uv=str(fake_uv), output=tmp_path / "x"
        )


def test_resolve_target_compiles_without_writing_a_lock(repo, fake_uv):
    catalog = discover(repo)

    text = resolve_target(catalog.targets["alpha"], catalog, root=repo, uv=str(fake_uv))

    assert "numpy>=2" in text
    assert not (repo / "tests/locks/alpha.lock").exists()
