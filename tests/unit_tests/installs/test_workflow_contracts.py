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

"""CI workflows keep the checks the repository rules and releases rely on.

The scopes these workflows pass around are covered by ``test_affected``; these
tests read the workflow files themselves, because a dropped trigger, a missing
``needs``, or a widened wheel scope is invisible to a Python import. They belong
with the repository install data because the workflows are the readers of that
data.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(workflow):
    # YAML 1.1 reads the top-level ``on:`` key as the boolean True.
    for key in ("on", True):
        if key in workflow:
            return workflow[key]
    raise AssertionError("workflow has no trigger section")


def _steps(workflow, job):
    return workflow["jobs"][job]["steps"]


def _step(workflow, job, name):
    for step in _steps(workflow, job):
        if step.get("name") == name:
            return step
    raise AssertionError(f"job {job!r} has no step {name!r}")


def test_fast_ci_runs_on_every_pull_request():
    triggers = _triggers(_workflow("fast-ci.yml"))

    # A ``paths:`` filter would leave the required check pending instead of
    # skipping, so the workflow must always start and narrow inside the scope
    # job.
    assert "paths" not in triggers["pull_request"]
    assert "paths" not in triggers["push"]
    assert triggers["push"]["branches"] == ["main"]


def test_fast_ci_has_one_aggregate_required_check():
    workflow = _workflow("fast-ci.yml")
    aggregate = workflow["jobs"]["unittest"]

    assert aggregate["if"] == "always()"
    assert set(aggregate["needs"]) == {"changes", "unit", "package", "full"}
    results = _steps(workflow, "unittest")[0]["run"]
    for job in ("changes", "unit", "package", "full"):
        assert f"{job}:${{{{ needs.{job}.result }}}}" in results


def test_fast_ci_scopes_full_ci_with_the_pull_request_profiles():
    script = _step(_workflow("fast-ci.yml"), "changes", "Map changed paths to a scope")[
        "run"
    ]

    # A core change keeps the full profile set for nightly and release runs,
    # while a pull request installs the pilot set; a component change already
    # narrows ``profiles`` to its closure.
    assert 'scope.get("pr_profiles", scope["profiles"])' in script
    assert (
        'e2e = sorted(suites) if set(selected) == set(scope["profiles"]) else []'
        in (script)
    )
    # Install data changes narrow the profile set but still call full CI for
    # those profiles.
    assert 'bool(scope["components"] or scope["profiles"])' in script


def test_fast_ci_runs_installer_and_install_data_tests_in_the_dev_profile():
    workflow = _workflow("fast-ci.yml")

    # Both groups need only the core and `dev` dependencies; every other test
    # path may import a model server, which needs the CPU Torch profile.
    script = _step(workflow, "changes", "Map changed paths to a scope")["run"]
    assert '{"tests/unit_tests/rpent/install", "tests/unit_tests/installs"}' in script
    assert 'profile = "dev" if tests and tests <= dev_tests else "unit-cpu"' in script
    assert workflow["jobs"]["unit"]["with"]["profile"] == (
        "${{ needs.changes.outputs.profile }}"
    )


def test_fast_ci_checks_the_package_for_packaging_changes():
    script = _step(_workflow("fast-ci.yml"), "changes", "Map changed paths to a scope")[
        "run"
    ]

    # ``setup.py`` chooses the packages in the wheel and sdist, so it changes
    # what the package job has to verify.
    assert '{"pyproject.toml", "uv.lock", "setup.py", "MANIFEST.in"}' in script


def test_full_ci_does_not_run_on_tags():
    # A tag push used to start full CI and publish in parallel. The publish
    # workflow now calls full CI itself, so that it verifies the exact commit
    # it releases before building.
    triggers = _triggers(_workflow("full-ci.yml"))

    assert "push" not in triggers
    assert set(triggers) == {"schedule", "workflow_dispatch", "workflow_call"}


def test_full_ci_lock_check_gates_a_release():
    workflow = _workflow("full-ci.yml")

    assert workflow["jobs"]["locks"]["if"] == "inputs.full == true"
    assert workflow["jobs"]["unit"]["with"]["profile"] == "unit-cpu"
    called = _step(workflow, "scope", "Select the profiles and suites")["run"]
    assert '"$EVENT" == "workflow_call" && "$CALLED_FULL" != "true"' in called


def test_publish_verifies_before_building_the_core_wheel():
    workflow = _workflow("publish.yml")

    assert _triggers(workflow)["push"]["tags"] == ["v*"]
    assert workflow["jobs"]["verify"]["uses"] == "./.github/workflows/full-ci.yml"
    assert workflow["jobs"]["verify"]["with"] == {"full": True}
    assert workflow["jobs"]["build"]["needs"] == "verify"
    assert workflow["jobs"]["publish"]["needs"] == "build"
    assert _step(workflow, "build", "Build sdist and wheel")["env"][
        "RPENT_WHEEL_SCOPE"
    ] == ("core")


def test_package_checks_the_core_wheel_and_the_complete_sdist():
    workflow = _workflow("package.yml")

    assert _step(workflow, "build", "Build sdist and wheel")["env"][
        "RPENT_WHEEL_SCOPE"
    ] == ("core")
    wheel_check = _step(workflow, "build", "Check the wheel install")["run"]
    assert "robots" in wheel_check and "components" in wheel_check
    # The sdist is the supported source install, so it must carry the component
    # packages the wheel deliberately omits.
    sdist = _step(workflow, "build", "Install the sdist and upgrade it to the wheel")[
        "run"
    ]
    assert "import components" in sdist
    assert "import robots" in sdist
    source = _step(workflow, "build", "Check source installs outside the checkout")[
        "run"
    ]
    # A source-scope wheel is what `pip install .` produces; it must carry the
    # files the installed package opens, and an editable install must expose
    # the checkout's packages and profiles from another directory.
    assert "--no-deps -e ." in source
    for relative in ("target50.json", "demo_randomized.json", "report_template.md"):
        assert relative in source
    assert "rpent-install" in source


def test_unit_workflow_defaults_to_the_cpu_profile():
    workflow = _workflow("unit.yml")
    inputs = _triggers(workflow)["workflow_call"]["inputs"]

    # ``dev`` deliberately has no Torch; the CPU profile supplies it so the
    # full unit suite can import model servers.
    assert inputs["profile"]["default"] == "unit-cpu"
    cache_key = _step(workflow, "unit", "Restore the prebuilt environment")["with"][
        "key"
    ]
    assert "inputs.profile" in cache_key
    assert _step(workflow, "unit", "Report skipped tests")["if"] == "always()"
