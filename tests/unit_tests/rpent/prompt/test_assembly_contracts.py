# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rpent.prompt.artifacts import (
    EFFECTIVE_PROMPT,
    PROMPT_SOURCES,
    write_prompt_artifacts,
)
from rpent.prompt.assembly import (
    PromptLayers,
    PromptSection,
    assemble_prompt,
    build_robot_prompt,
    fragment,
    mode_sections,
    prompt_sha256,
    run_modes,
)
from rpent.prompt.utils import format_prompt
from rpent.robots.prompt_bundle import PromptBundle


def _layers() -> PromptLayers:
    return PromptLayers(
        base=(fragment("base", "OPERATING RULES"),),
        mode=mode_sections(("evaluate",)),
        tools=(PromptSection("TOOL", "tool guidance", "robot/tools.py"),),
        domain=(PromptSection("DOMAIN", "domain knowledge", "robot/domain.py"),),
        memory=(fragment("memory_protocol", "MEMORY — HOW TO READ"),),
    )


def test_assemble_prompt_renders_fixed_layer_order() -> None:
    assembled = assemble_prompt(
        _layers(),
        user=(PromptSection("TASK", "task", "robot/user.py", role="user"),),
        variables={},
    )

    titles = [section["name"] for section in assembled.sections]
    assert titles == [
        "OPERATING RULES",
        "RUN MODE — EVALUATION",
        "TOOL",
        "DOMAIN",
        "MEMORY — HOW TO READ",
        "TASK",
    ]
    assert assembled.system.index("OPERATING RULES") < assembled.system.index(
        "tool guidance"
    )
    assert assembled.system.index("tool guidance") < assembled.system.index(
        "domain knowledge"
    )
    assert assembled.user == "task\n"
    assert assembled.prompt_sha256 == prompt_sha256(assembled.system, assembled.user)


def test_assemble_prompt_is_deterministic_and_rejects_duplicates() -> None:
    first = assemble_prompt(_layers(), variables={})
    second = assemble_prompt(_layers(), variables={})
    assert first.prompt_sha256 == second.prompt_sha256

    duplicate = PromptLayers(
        domain=(
            PromptSection("SAME", "one", "a.py"),
            PromptSection("SAME", "two", "b.py"),
        )
    )
    with pytest.raises(ValueError, match="duplicate prompt section"):
        assemble_prompt(duplicate, variables={})
    with pytest.raises(ValueError, match="unknown prompt mode"):
        mode_sections(("typo",))


def test_run_modes_and_memory_sections_follow_the_run() -> None:
    assert run_modes(explore=False, dashboard=False, real_robot=False) == ("evaluate",)
    assert run_modes(explore=True, dashboard=True, real_robot=True) == (
        "explore",
        "dashboard",
        "real_robot",
    )

    names = [section.name for section in mode_sections(("evaluate", "real_robot"))]
    assert names == ["RUN MODE — EVALUATION", "RUN MODE — REAL ROBOT"]


def test_fragments_do_not_depend_on_robot_variables() -> None:
    for stem in (
        "base",
        "mode_evaluate",
        "mode_explore",
        "mode_dashboard",
        "mode_real_robot",
        "memory_protocol",
        "memory_proposals",
    ):
        assert "{{" not in format_prompt(fragment(stem, stem).node)


def test_build_robot_prompt_contributes_domain_tools_and_memory() -> None:
    bundle = PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: {"TASK": "user task"},
        prompt_sections=lambda variables: {"TOOL": "tool knowledge"},
        source="robots/demo/prompts",
    )
    variables = {
        "memory_dir": "/memory",
        "task": "demo",
    }
    assembled = build_robot_prompt(
        bundle,
        robot_name="demo",
        variables=variables,
        modes=("explore",),
    )

    assert "tool knowledge" in assembled.system
    assert "domain knowledge" in assembled.system
    assert "memory" in assembled.system.lower()
    assert "inbox" in assembled.system.lower()
    assert "TASK" in assembled.user
    assert "user task" in assembled.user
    assert {section["source"] for section in assembled.sections} >= {
        "robots/demo/prompts",
        "rpent/prompt/fragments/base.md",
        "rpent/prompt/fragments/memory_protocol.md",
    }

    without_memory = build_robot_prompt(
        bundle,
        robot_name="demo",
        variables={"task": "demo"},
        modes=("evaluate",),
    )
    assert "MEMORY — HOW TO READ" not in without_memory.system


def test_write_prompt_artifacts_records_layout_and_sources(tmp_path: Path) -> None:
    assembled = assemble_prompt(_layers(), variables={})
    prompt_path, sources_path = write_prompt_artifacts(
        tmp_path,
        assembled=assembled,
        robot_name="demo",
        planner="claude_code",
        modes=("evaluate",),
        user_message="do the task",
    )

    assert prompt_path == tmp_path / EFFECTIVE_PROMPT
    assert sources_path == tmp_path / PROMPT_SOURCES
    text = prompt_path.read_text(encoding="utf-8")
    assert "prompt_sha256" in text
    assert assembled.system.rstrip("\n") in text
    assert "do the task" in text

    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    assert sources["planner_prompt_layout"] == "system_prefixed_to_user"
    assert sources["modes"] == ["evaluate"]
    assert sources["prompt_sha256"] == assembled.prompt_sha256
    assert sources["user_message_sha256"] == hashlib.sha256(b"do the task").hexdigest()
    assert [section["name"] for section in sources["sections"]] == [
        section["name"] for section in assembled.sections
    ]
