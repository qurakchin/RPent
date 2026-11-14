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

from rpent.prompt.assembly import (
    PromptLayers,
    PromptSection,
    assemble_prompt,
    build_robot_prompt,
    fragment,
    prefix_system_prompt,
    prompt_sha256,
    run_axes,
    section_source,
)
from rpent.prompt.prompt_artifacts import (
    EFFECTIVE_PROMPT,
    PROMPT_SOURCES,
    delivered_prompt_text,
    effective_prompt_markdown,
    prompt_sources,
    write_prompt_artifacts,
)
from rpent.prompt.utils import format_prompt
from rpent.robots.prompt_bundle import PromptBundle


def _layers() -> PromptLayers:
    return PromptLayers(
        base=(fragment("base", "OPERATING RULES"),),
        axis=(fragment("mode_evaluate", "RUN MODE — EVALUATION"),),
        tools=(PromptSection("TOOL", "tool guidance", "robot/tools.py"),),
        domain=(PromptSection("DOMAIN", "domain knowledge", "robot/domain.py"),),
        memory=(fragment("memory_protocol", "MEMORY — HOW TO READ"),),
    )


def test_prompt_bundle_render_keeps_the_pre_assembly_api() -> None:
    bundle = PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: "user task",
    )

    assert "domain knowledge" in bundle.render("system")
    assert bundle.render("user", variables={}) == "user task\n"

    # Section contributions need their layer and provenance; rendering them as
    # one bare node would silently drop both.
    with pytest.raises(ValueError, match="assemble_prompt"):
        PromptBundle(
            system=lambda variables: (PromptSection("X", "x", "robot/domain.py"),),
            user=lambda variables: "user task",
        ).render("system")


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


def test_section_source_falls_back_to_the_outermost_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed slice outside the repository root still gets a stable path."""
    root = tmp_path / "site-packages"
    prompts = root / "robots" / "demo" / "prompts"
    prompts.mkdir(parents=True)
    for package in (root / "robots", root / "robots" / "demo", prompts):
        (package / "__init__.py").write_text("", encoding="utf-8")
    module = prompts / "tools.py"
    module.write_text("", encoding="utf-8")
    monkeypatch.setenv("RPENT_REPO_ROOT", str(tmp_path / "elsewhere"))

    assert section_source(module) == "robots/demo/prompts/tools.py"


def test_sections_that_render_empty_are_not_recorded_as_sources() -> None:
    """A conditional contribution the model never saw is not provenance."""
    assembled = assemble_prompt(
        PromptLayers(
            domain=(
                PromptSection("PRESENT", "text", "robot/domain.py"),
                PromptSection("ABSENT", "", "robot/domain.py"),
            )
        ),
        variables={},
    )

    assert [section["name"] for section in assembled.sections] == ["PRESENT"]
    assert assembled.system == "text\n"


def test_section_digest_covers_the_bytes_the_section_contributes() -> None:
    section = PromptSection("ONLY", "line one\nline two\n", "robot/domain.py")
    assembled = assemble_prompt(PromptLayers(domain=(section,)), variables={})

    assert assembled.system == "line one\nline two\n"
    assert (
        assembled.sections[0]["sha256"]
        == hashlib.sha256(b"line one\nline two").hexdigest()
    )


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

    with pytest.raises(ValueError, match="unknown prompt axis"):
        build_robot_prompt(
            _bundle(),
            robot_name="demo",
            variables={},
            axes=("typo",),
        )


def _bundle() -> PromptBundle:
    return PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: {"TASK": "user task"},
    )


def test_run_axes_and_memory_sections_follow_the_run() -> None:
    assert run_axes(explore=False, dashboard=False, real_robot=False) == ("evaluate",)
    assert run_axes(explore=True, dashboard=True, real_robot=True) == (
        "explore",
        "interactive",
        "real_robot",
    )

    assembled = build_robot_prompt(
        _bundle(),
        robot_name="demo",
        variables={},
        axes=("evaluate", "interactive", "real_robot"),
    )
    names = [section["name"] for section in assembled.sections]
    assert names[1:4] == [
        "RUN MODE — EVALUATION",
        "RUN MODE — INTERACTIVE",
        "RUN MODE — REAL ROBOT",
    ]


def test_fragments_do_not_depend_on_robot_variables() -> None:
    for stem in (
        "base",
        "mode_evaluate",
        "mode_explore",
        "interactive",
        "real_robot",
        "memory_protocol",
        "memory_proposals",
        "memory_transfer",
    ):
        assert "{{" not in format_prompt(fragment(stem, stem).node)


def test_build_robot_prompt_contributes_domain_tools_and_memory(
    tmp_path: Path,
) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    bundle = PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: {"TASK": "user task"},
        tool_sections=lambda variables: {"TOOL": "tool knowledge"},
        source="robots/demo/prompts",
    )
    variables = {
        "memory_dir": str(memory_dir),
        "task": "demo",
    }
    assembled = build_robot_prompt(
        bundle,
        robot_name="demo",
        variables=variables,
        axes=("explore",),
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
        axes=("evaluate",),
    )
    assert "MEMORY — HOW TO READ" not in without_memory.system


def test_write_prompt_artifacts_records_layout_and_sources(tmp_path: Path) -> None:
    assembled = assemble_prompt(_layers(), variables={})
    prompt_path, sources_path = write_prompt_artifacts(
        tmp_path,
        assembled=assembled,
        robot_name="demo",
        planner="claude_code",
        axes=("evaluate",),
        user_message="do the task",
    )

    assert prompt_path == tmp_path / EFFECTIVE_PROMPT
    assert sources_path == tmp_path / PROMPT_SOURCES
    text = prompt_path.read_text(encoding="utf-8")
    assert "prompt_sha256" in text
    assert assembled.system.rstrip("\n") in text
    assert "do the task" in text

    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    assert sources["planner_prompt_layout"] == "separate_system"
    assert sources["axes"] == ["evaluate"]
    assert sources["prompt_sha256"] == assembled.prompt_sha256
    assert sources["user_message_sha256"] == hashlib.sha256(b"do the task").hexdigest()
    assert "delivered_sha256" not in sources
    assert f"user_message_sha256: `{sources['user_message_sha256']}`" in text
    assert [section["name"] for section in sources["sections"]] == [
        section["name"] for section in assembled.sections
    ]
    assert not list(tmp_path.glob(".*.tmp"))


def test_prompt_sources_hash_the_delivered_message_for_prefixing_planners() -> None:
    assembled = assemble_prompt(_layers(), variables={})
    user_message = "do the task"

    sources = prompt_sources(
        assembled,
        robot_name="demo",
        planner="codex",
        axes=("evaluate",),
        user_message=user_message,
    )

    delivered = prefix_system_prompt(assembled.system, user_message)
    assert (
        sources["user_message_sha256"]
        == hashlib.sha256(user_message.encode("utf-8")).hexdigest()
    )
    assert (
        sources["delivered_sha256"]
        == hashlib.sha256(delivered.encode("utf-8")).hexdigest()
    )
    text = effective_prompt_markdown(
        assembled,
        robot_name="demo",
        planner="codex",
        axes=("evaluate",),
        user_message=user_message,
    )
    assert f"delivered_sha256: `{sources['delivered_sha256']}`" in text


def test_delivered_text_uses_the_same_prefix_helper_as_the_planners() -> None:
    system, user = "system text\n", "user text\n"

    # Codex and the artifact both call this helper.
    assert prefix_system_prompt(system, user) == f"{system}\n\n{user}"
    assert delivered_prompt_text("codex", system=system, user=user) == (
        prefix_system_prompt(system, user)
    )

    # api and claude_code send two roles; flash never receives the prompt.
    assert delivered_prompt_text("api", system=system, user=user) is None
    assert delivered_prompt_text("claude_code", system=system, user=user) is None
    assert delivered_prompt_text("flash", system=system, user=user) is None
    assert prefix_system_prompt("", user) == user


def test_bundle_assembly_keeps_the_declared_layer_order(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    bundle = PromptBundle(
        system=lambda variables: {"DOMAIN": "domain knowledge"},
        user=lambda variables: {"TASK": "user task"},
        tool_sections=lambda variables: {"TOOL": "tool knowledge"},
        source="robots/demo/prompts",
    )
    assembled = build_robot_prompt(
        bundle,
        robot_name="demo",
        variables={"memory_dir": str(memory_dir)},
        axes=run_axes(explore=True, dashboard=False, real_robot=True),
    )

    assert [section["name"] for section in assembled.sections] == [
        "OPERATING RULES",
        "RUN MODE — EXPLORATION",
        "RUN MODE — REAL ROBOT",
        "TOOL",
        "DOMAIN",
        "MEMORY — HOW TO READ",
        "MEMORY — USING STORED EVIDENCE",
        "MEMORY — PROPOSALS AND MERGING",
        "TASK",
    ]


def test_memory_proposal_fragment_names_the_fields_the_merge_validates() -> None:
    from rpent.memory.manager import _validate

    text = format_prompt(fragment("memory_proposals", "proposals").node)
    for field in (
        "id",
        "scope",
        "confidence",
        "evidence.cells",
        "task-family",
        "global",
        "suite",
        "regime",
        "task_id",
        "task_language",
        "kind",
        "title",
        "applies_when",
    ):
        assert field in text

    valid = {
        "scope": "global",
        "kind": "strategy",
        "confidence": "single-shot",
        "title": "t",
        "applies_when": "when",
    }
    with pytest.raises(ValueError, match="evidence.cells"):
        _validate(dict(valid, evidence={"cells": []}))
    _validate(dict(valid, evidence={"cells": ["cell"]}))
