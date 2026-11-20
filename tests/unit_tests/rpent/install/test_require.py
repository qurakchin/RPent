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

"""Optional dependency guards name the owning component and installation hint."""

import importlib
import json
from pathlib import Path

import pytest

# ``rpent.install.require`` is also re-exported as a function from the package,
# so bind the module explicitly to monkeypatch its vendored helpers.
components = importlib.import_module("rpent.install.require")


def _inside(fingerprint, monkeypatch):
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)


def test_require_returns_an_importable_module():
    assert components.require("alpha", "json") is json


def test_missing_module_names_component_and_install(monkeypatch):
    monkeypatch.setattr(components, "current_venv", lambda: None)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("model-sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert (
        "component 'model-sam3' requires 'definitely_missing_rpent_module'" in message
    )
    assert "rpent-install install model-sam3" in message


def test_installed_component_repairs_its_environment(monkeypatch):
    fingerprint = {
        "environment": "alpha",
        "requested": ["alpha"],
        "components": {"model-sam3": {"manifest_sha256": "sha"}},
    }
    _inside(fingerprint, monkeypatch)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("model-sam3", "definitely_missing_rpent_module")

    assert (
        "rerun `rpent-install install alpha --venv /venv` to repair the environment"
        in str(error.value)
    )


def test_component_outside_environment_keeps_the_installed_components(monkeypatch):
    # Adding a component to an installed environment must keep the components
    # already requested there, or the command would describe a different
    # environment than the one being repaired.
    fingerprint = {
        "environment": "robot-alpha",
        "requested": ["robot-alpha"],
        "components": {},
    }
    _inside(fingerprint, monkeypatch)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("model-sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "is not part of environment 'robot-alpha'" in message
    assert "`rpent-install install robot-alpha model-sam3 --venv /venv`" in message


def test_component_outside_a_composition_extends_it(monkeypatch):
    fingerprint = {
        "environment": "infra-dev+robot-alpha",
        "requested": ["infra-dev", "robot-alpha"],
        "components": {},
    }
    _inside(fingerprint, monkeypatch)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("model-sam3", "definitely_missing_rpent_module")

    assert (
        "`rpent-install install infra-dev robot-alpha model-sam3 --venv /venv`"
        in str(error.value)
    )


def test_fingerprint_without_requested_falls_back_to_the_component(monkeypatch):
    # A fingerprint written before components were recorded has no request to
    # extend; the hint must name a real install command rather than "None" or
    # an empty argument.
    fingerprint = {
        "environment": "minimal",
        "components": {"model-sam3": {"manifest_sha256": "sha"}},
    }
    _inside(fingerprint, monkeypatch)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("model-sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "rerun `rpent-install install model-sam3 --venv /venv`" in message
    assert "None" not in message
