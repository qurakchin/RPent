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

"""A declared lock must cover and satisfy the profile's direct requirements."""

import pytest

from rpent.install.locks import lock_problems, parse_lock
from rpent.install.manifest import Selection
from rpent.install.resolve import resolve


def _resolution(make_component, make_profile, make_catalog, dependencies):
    component = make_component("alpha", dependencies=list(dependencies))
    profile = make_profile(
        "alpha", {"alpha": Selection()}, lock="envs/locks/alpha.lock"
    )
    catalog = make_catalog(components=[component], profiles={"alpha": profile})
    return profile, resolve(profile, catalog)


def _write_lock(tmp_path, text):
    path = tmp_path / "envs/locks/alpha.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_lock_reads_pins_and_direct_urls():
    entries = parse_lock(
        "# comment\n"
        "--index-url https://example.test/simple\n"
        "numpy==2.0.0\n"
        "OpenPI-Client @ git+https://github.com/RLinf/openpi.git@abc\n"
    )

    assert str(entries["numpy"].specifier) == "==2.0.0"
    assert entries["openpi-client"].url is not None


def test_undeclared_lock_is_not_checked(
    make_component, make_profile, make_catalog, tmp_path
):
    component = make_component("alpha", dependencies=["numpy>=2"])
    profile = make_profile("alpha", {"alpha": Selection()})
    catalog = make_catalog(components=[component], profiles={"alpha": profile})
    resolution = resolve(profile, catalog)

    assert lock_problems(profile, resolution, tmp_path) == []


def test_missing_declared_lock_is_reported(
    make_component, make_profile, make_catalog, tmp_path
):
    profile, resolution = _resolution(
        make_component, make_profile, make_catalog, ["numpy>=2"]
    )

    problems = lock_problems(profile, resolution, tmp_path)

    assert problems == [
        "profile 'alpha' declares lock envs/locks/alpha.lock, but the file does "
        "not exist; run `rpent-env lock alpha`"
    ]


def test_lock_covering_the_requirements_is_accepted(
    make_component, make_profile, make_catalog, tmp_path
):
    profile, resolution = _resolution(
        make_component,
        make_profile,
        make_catalog,
        [
            "numpy>=2",
            "rpent-openpi @ git+https://github.com/RLinf/openpi.git@rpent",
            "pyrealsense2; sys_platform == 'linux'",
        ],
    )
    _write_lock(
        tmp_path,
        "numpy==2.0.0\nrpent-openpi @ git+https://github.com/RLinf/openpi.git@abc123\n",
    )

    assert lock_problems(profile, resolution, tmp_path) == []


def test_lock_pin_that_violates_the_manifest_is_reported(
    make_component, make_profile, make_catalog, tmp_path
):
    profile, resolution = _resolution(
        make_component, make_profile, make_catalog, ["numpy>=2.1"]
    )
    _write_lock(tmp_path, "numpy==2.0.0\n")

    problems = lock_problems(profile, resolution, tmp_path)

    assert "pins numpy==2.0.0, which does not satisfy numpy>=2.1" in problems[0]


def test_lock_missing_a_requirement_is_reported(
    make_component, make_profile, make_catalog, tmp_path
):
    profile, resolution = _resolution(
        make_component, make_profile, make_catalog, ["numpy>=2", "packaging"]
    )
    _write_lock(tmp_path, "numpy==2.0.0\n")

    problems = lock_problems(profile, resolution, tmp_path)

    assert "does not cover 'packaging'" in problems[0]


def test_lock_from_another_repository_is_reported(
    make_component, make_profile, make_catalog, tmp_path
):
    profile, resolution = _resolution(
        make_component,
        make_profile,
        make_catalog,
        ["rpent-openpi @ git+https://github.com/RLinf/openpi.git@rpent"],
    )
    _write_lock(
        tmp_path,
        "rpent-openpi @ git+https://github.com/example/openpi.git@abc123\n",
    )

    problems = lock_problems(profile, resolution, tmp_path)

    assert "but the manifest requires" in problems[0]


@pytest.mark.parametrize("include_core", [True, False])
def test_core_requirements_are_checked_only_when_requested(
    make_component, make_profile, make_catalog, tmp_path, include_core
):
    profile, resolution = _resolution(
        make_component, make_profile, make_catalog, ["numpy>=2"]
    )
    _write_lock(tmp_path, "numpy==2.0.0\n")

    problems = lock_problems(
        profile,
        resolution,
        tmp_path,
        core_dependencies=("packaging>=24",) if include_core else (),
    )

    assert bool(problems) is include_core
