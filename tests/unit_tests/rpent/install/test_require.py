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


def test_require_returns_an_importable_module():
    assert components.require("alpha", "json") is json


def test_missing_module_names_component_and_install(monkeypatch):
    monkeypatch.setattr(components, "current_venv", lambda: None)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "component 'sam3' requires 'definitely_missing_rpent_module'" in message
    assert "rpent-env list" in message


def test_external_component_hint_names_its_environment(monkeypatch):
    fingerprint = {
        "profile": "alpha",
        "components": {
            "molmo": {"placement": "external-env", "profile": "molmo-server"}
        },
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("molmo", "definitely_missing_rpent_module")

    assert "external environment 'molmo-server'" in str(error.value)
    assert "rpent-env install molmo-server" in str(error.value)


def test_in_environment_component_repairs_its_profile(monkeypatch):
    fingerprint = {
        "profile": "alpha",
        "components": {"sam3": {"placement": "in-env"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    assert "rerun `rpent-env install alpha`" in str(error.value)


def test_component_outside_profile_points_to_a_development_install(monkeypatch):
    fingerprint = {"profile": "alpha", "components": {}}
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    assert "is not part of profile 'alpha'" in str(error.value)


def test_component_diagnostic_repairs_the_component(monkeypatch):
    # A component install records ``profile: null``; the hint must not tell the
    # user to rerun `rpent-env install None`.
    fingerprint = {
        "install_kind": "component",
        "profile": None,
        "component": "sam3",
        "components": {"sam3": {"placement": "in-env"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    assert "rerun `rpent-env install sam3`" in str(error.value)
    assert "None" not in str(error.value)


def test_missing_module_in_a_component_diagnostic_names_the_component(
    monkeypatch,
):
    fingerprint = {
        "install_kind": "component",
        "profile": None,
        "component": "sam3",
        "components": {"sam3": {"placement": "in-env"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("molmo", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "installed for component 'sam3'" in message
    assert "rpent-env install molmo" in message
