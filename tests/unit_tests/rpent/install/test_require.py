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
    assert "rpent-install list" in message


def test_remote_component_hint_names_its_own_target(monkeypatch):
    fingerprint = {
        "target": "robot-libero_pro",
        "components": {"molmo": {"placement": "remote"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("molmo", "definitely_missing_rpent_module")

    assert "runs outside target 'robot-libero_pro'" in str(error.value)
    assert "rpent-install install robot-libero_pro" in str(error.value)


def test_in_environment_component_repairs_its_target(monkeypatch):
    fingerprint = {
        "target": "alpha",
        "components": {"sam3": {"placement": "in-env"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    assert "rerun `rpent-install install alpha`" in str(error.value)


def test_component_outside_target_points_to_a_development_install(monkeypatch):
    fingerprint = {"target": "alpha", "components": {}}
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    assert "is not part of target 'alpha'" in str(error.value)


def test_missing_component_names_the_targets_that_include_it(monkeypatch):
    fingerprint = {"target": "minimal", "components": {}}
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)
    monkeypatch.setattr(
        components,
        "_targets_by_component",
        lambda: {"sam3": ["dev", "libero-pro", "sam3-server"]},
    )

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "is not part of target 'minimal'" in message
    assert "dev, libero-pro, sam3-server" in message


def test_target_index_comes_from_the_checkout(monkeypatch):
    # The repair hint reads the manifests instead of an index stored with the
    # installation, so a target added after that environment was installed is
    # still offered.
    monkeypatch.setattr(components, "_TARGETS_BY_COMPONENT", None)

    index = components._targets_by_component()

    assert "robot-libero_pro" in index["sam3"]


def test_fingerprint_without_a_target_falls_back_to_the_general_hint(monkeypatch):
    # A fingerprint written by the removed component install records
    # ``target: null``; the hint must not tell the user to install target None.
    fingerprint = {
        "install_kind": "component",
        "target": None,
        "component": "sam3",
        "components": {"sam3": {"placement": "in-env"}},
    }
    monkeypatch.setattr(components, "current_venv", lambda: Path("/venv"))
    monkeypatch.setattr(components, "read_fingerprint", lambda venv: fingerprint)

    with pytest.raises(components.MissingComponentError) as error:
        components.require("sam3", "definitely_missing_rpent_module")

    message = str(error.value)
    assert "rpent-install list" in message
    assert "None" not in message
