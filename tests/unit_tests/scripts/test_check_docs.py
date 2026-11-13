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

"""Contract tests for scripts/check_docs.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_docs.py"


def run(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker against a temporary repository root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def write(root: Path, name: str, text: str = "") -> Path:
    """Write a file below the temporary root."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_markdown_links_and_anchors(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[ok](other.md#validation-status) [bad](missing.md)\n",
    )
    write(tmp_path, "docs/other.md", "## Validation status\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "broken link target 'missing.md'" in result.stdout
    assert "other.md" not in result.stdout


def test_missing_markdown_heading_anchor(tmp_path: Path) -> None:
    write(tmp_path, "docs/page.md", "[bad](other.md#no-such-heading)\n")
    write(tmp_path, "docs/other.md", "## Validation status\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "missing heading anchor #no-such-heading" in result.stdout


def test_rst_doc_and_ref_roles(tmp_path: Path) -> None:
    write(tmp_path, "docs/source-en/conf.py")
    write(tmp_path, "docs/source-en/index.rst", "Index\n=====\n")
    write(
        tmp_path,
        "docs/source-en/page.rst",
        "Page\n====\n\n"
        ".. _known-label:\n\n"
        "See :doc:`index` and :ref:`known-label`.\n"
        "Bad :doc:`missing` and :ref:`unknown-label`.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "broken :doc: target 'missing'" in result.stdout
    assert "unknown :ref: label 'unknown-label'" in result.stdout
    assert "known-label`" not in result.stdout


def test_rst_directive_path(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/page.rst",
        "Page\n====\n\n.. figure:: missing.png\n   :alt: missing\n",
    )
    write(tmp_path, "docs/source-en/conf.py")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "broken RST path 'missing.png'" in result.stdout


def test_documented_command_paths(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/run.md",
        "```bash\npytest tests/missing -v\nbash docs/run.sh\n```\n",
    )
    write(tmp_path, "docs/run.sh")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "documented path 'tests/missing' does not exist" in result.stdout
    assert "docs/run.sh" not in result.stdout


def test_external_checkout_commands_are_skipped(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/setup.md",
        "```bash\n"
        "cd /path/to/other-checkout\n"
        "bash requirements/install.sh embodied\n"
        "```\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_optional_dependency_names(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        "[project]\nname = 'demo'\n\n"
        "[project.optional-dependencies]\n"
        "test = []\n"
        "robot = []\n",
    )
    write(
        tmp_path,
        "docs/install.md",
        "```bash\n"
        'uv pip install -e ".[test,robot]"\n'
        'uv pip install -e ".[missing]"\n'
        "```\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "unknown optional dependency 'missing'" in result.stdout
    assert "unknown optional dependency 'test'" not in result.stdout


def test_ignore_marker_and_external_urls(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[site](https://example.com/missing)\n"
        "[planned](not-yet.md) <!-- docs-check: ignore: planned for the next release -->\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_markdown_reference_style_links(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[ok][existing]\n[bad][missing]\n\n[existing]: other.md\n[gone]: nowhere.md\n",
    )
    write(tmp_path, "docs/other.md", "# Other\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "broken link target 'nowhere.md'" in result.stdout
    assert "missing Markdown link definition [missing]" in result.stdout
    assert "other.md" not in result.stdout


def test_pip_install_extras(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        "[project]\nname = 'demo'\n\n[project.optional-dependencies]\ntest = []\n",
    )
    write(
        tmp_path,
        "docs/install.md",
        "```bash\n"
        'pip install -e ".[missing]"\n'
        'python -m pip install -e ".[test]"\n'
        "```\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "unknown optional dependency 'missing'" in result.stdout
    assert "unknown optional dependency 'test'" not in result.stdout


def test_inline_command_paths(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "Run `bash docs/missing.sh` to start.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "documented path 'docs/missing.sh' does not exist" in result.stdout


def test_ignore_marker_applies_to_the_next_line(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.rst",
        "Page\n====\n\n"
        ".. docs-check: ignore: example command\n"
        "\n"
        "Run ``bash docs/missing.sh`` to start.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_ignore_marker_on_content_line_hides_only_that_line(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[site](https://example.com) <!-- docs-check: ignore: external -->\n"
        "Run `bash docs/missing.sh` to start.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "documented path 'docs/missing.sh' does not exist" in result.stdout


def test_rst_tree_absolute_paths(tmp_path: Path) -> None:
    write(tmp_path, "docs/source-en/conf.py")
    write(
        tmp_path,
        "docs/source-en/page.rst",
        "Page\n====\n\n"
        ".. image:: /_static/missing.png\n"
        ".. image:: /_static/present.png\n",
    )
    write(tmp_path, "docs/source-en/_static/present.png")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "broken RST path '/_static/missing.png'" in result.stdout
    assert "present.png" not in result.stdout


def test_missing_cd_target_is_reported(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/setup.md",
        "```bash\ncd missing-dir\nbash requirements/install.sh\n```\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "documented cd target 'missing-dir' does not exist" in result.stdout


def test_clone_directory_name_resolves_to_repository_root(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[project]\nname = 'demo'\n")
    write(
        tmp_path,
        "docs/setup.md",
        "```bash\ncd Demo\nbash docs/missing.sh\n```\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "documented cd target 'Demo' does not exist" not in result.stdout
    assert "documented path 'docs/missing.sh' does not exist" in result.stdout


def test_validation_status_vocabulary_and_evidence(tmp_path: Path) -> None:
    prefix = (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/unsupported.rst",
        prefix
        + "   * - Offline checks\n"
        + "     - Supported\n"
        + "     - Some run.\n",
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/no-evidence.rst",
        prefix + "   * - Offline checks\n" + "     - CPU only\n" + "     -\n",
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/valid.rst",
        prefix
        + "   * - Offline checks\n"
        + "     - CPU only\n"
        + "     - Offline checks passed.\n",
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/trailing.rst",
        prefix
        + "   * - Offline checks\n"
        + "     - CPU only\n"
        + "     - Offline checks passed.\n"
        + "\nExtra\n-----\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "unknown validation status 'Supported'" in result.stdout
    assert "validation row 'CPU only' has no evidence" in result.stdout
    assert "Validation Status must be the last section" in result.stdout
    assert "valid.rst" not in result.stdout


def test_validation_evidence_paths_must_exist(tmp_path: Path) -> None:
    prefix = (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/fabricated.rst",
        prefix
        + "   * - Offline checks\n"
        + "     - CPU only\n"
        + "     - See ``missing/path/never-exists.md``.\n",
    )
    write(tmp_path, "docs/evidence.md")
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/present.rst",
        prefix
        + "   * - Offline checks\n"
        + "     - CPU only\n"
        + "     - See ``docs/evidence.md``.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert (
        "evidence path 'missing/path/never-exists.md' does not exist" in result.stdout
    )
    assert "present.rst" not in result.stdout


def test_validation_pages_require_language_counterpart(tmp_path: Path) -> None:
    prefix = (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/english_only.rst",
        prefix + "   * - Offline checks\n" + "     - CPU only\n" + "     - Ran.\n",
    )
    write(
        tmp_path,
        "docs/source-zh/rst_source/simulators/other.rst",
        prefix + "   * - 离线检查\n" + "     - 仅 CPU\n" + "     - 已运行。\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert (
        "missing Chinese counterpart "
        "'docs/source-zh/rst_source/simulators/english_only.rst'" in result.stdout
    )
    assert (
        "missing English counterpart "
        "'docs/source-en/rst_source/simulators/other.rst'" in result.stdout
    )


def test_paired_validation_pages_must_agree_on_statuses(tmp_path: Path) -> None:
    prefix = (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/demo.rst",
        prefix + "   * - Offline checks\n" + "     - CPU only\n" + "     - Ran.\n",
    )
    write(
        tmp_path,
        "docs/source-zh/rst_source/simulators/demo.rst",
        prefix + "   * - 离线检查\n" + "     - 未验证\n" + "     - 未运行。\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "validation statuses differ from the Chinese counterpart" in result.stdout


def test_historical_result_is_a_validation_status(tmp_path: Path) -> None:
    prefix = (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/demo.rst",
        prefix
        + "   * - Benchmark success\n"
        + "     - Historical result\n"
        + "     - Recorded on a frozen snapshot.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_design_status_without_git_warns(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/design/a_9_demo.md",
        "# Demo\n> 状态：草案｜基线 `deadbeef`｜最后更新 2026-11-13\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert (
        "warning: docs/design/a_9_demo.md:2: no Git history: "
        "design baseline commits were not checked" in result.stdout
    )


def test_design_status_in_shallow_clone_warns(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(origin),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        check=True,
    )
    baseline = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(shallow)],
        check=True,
    )
    write(
        shallow,
        "docs/design/a_9_demo.md",
        f"# Demo\n> 状态：草案｜基线 `{baseline}`｜最后更新 2026-11-13\n",
    )

    result = run(shallow)

    assert result.returncode == 0, result.stdout
    assert "shallow checkout: design baseline commits were not checked" in result.stdout


def test_missing_validation_status_section(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-zh/rst_source/real_world_robots/demo.rst",
        "Demo\n====\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "missing Validation Status / 验证状态 section" in result.stdout


def test_design_status_rejects_unreachable_baseline(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write(
        tmp_path,
        "docs/design/a_9_demo.md",
        "# Demo\n> 状态：草案｜基线 `deadbeef`｜最后更新 2026-13-01\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "baseline commit 'deadbeef' is not in this repository" in result.stdout
    assert "invalid status date '2026-13-01'" in result.stdout


def test_design_status_requires_a_status_line(tmp_path: Path) -> None:
    write(tmp_path, "docs/design/a_9_demo.md", "# Demo\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "missing design status line" in result.stdout


def test_valid_repository_is_clean(tmp_path: Path) -> None:
    write(tmp_path, "docs/README.md", "[page](page.md)\n")
    write(tmp_path, "docs/page.md", "# Page\n")

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "2 file(s) checked" in result.stdout
