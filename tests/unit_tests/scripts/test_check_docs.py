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


def run(root: Path, *files: str) -> subprocess.CompletedProcess[str]:
    """Run the checker against a temporary repository root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *files],
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


def validation_page(status: str = "CPU only", evidence: str = "Ran.") -> str:
    """Return an RST page with a minimal validation table."""
    return (
        "Demo\n====\n\n"
        "Validation Status\n-----------------\n\n"
        ".. list-table::\n"
        "   :header-rows: 1\n\n"
        "   * - Tier\n"
        "     - Status\n"
        "     - Evidence\n"
        "   * - Offline checks\n"
        f"     - {status}\n"
        f"     - {evidence}\n"
    )


def test_markdown_links(tmp_path: Path) -> None:
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


def test_same_file_heading_anchor_is_an_error(tmp_path: Path) -> None:
    write(tmp_path, "docs/page.md", "# Page\n\n[bad](#no-such-heading)\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "missing heading anchor #no-such-heading" in result.stdout


def test_cross_file_heading_anchor_is_a_warning(tmp_path: Path) -> None:
    write(tmp_path, "docs/page.md", "[maybe](other.md#no-such-heading)\n")
    write(tmp_path, "docs/other.md", "## Validation status\n")

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "warning: docs/page.md:1: heading anchor #no-such-heading" in result.stdout


def test_rst_references_are_left_to_sphinx(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/page.rst",
        "Page\n====\n\n"
        "See :doc:`missing`, :ref:`unknown-label`, and :download:`gone.txt`.\n\n"
        ".. figure:: missing.png\n   :alt: missing\n",
    )
    write(tmp_path, "docs/source-en/conf.py")

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


def test_validation_status_vocabulary_and_evidence(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/unsupported.rst",
        validation_page("Supported", "Some run."),
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/no-evidence.rst",
        validation_page("CPU only", ""),
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/valid.rst",
        validation_page(),
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/trailing.rst",
        validation_page() + "\nExtra\n-----\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "unknown validation status 'Supported'" in result.stdout
    assert "validation row 'CPU only' has no evidence" in result.stdout
    assert "Validation Status must be the last section" in result.stdout
    assert "valid.rst" not in result.stdout


def test_experimental_is_a_stability_tag_not_an_evidence_level(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/tagged.rst",
        validation_page("CPU only (Experimental)", "Ran."),
    )
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/bare.rst",
        validation_page("Experimental", "Ran."),
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "unknown validation status 'Experimental'" in result.stdout
    assert "tagged.rst" not in result.stdout


def test_validation_evidence_paths_must_exist(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/fabricated.rst",
        validation_page("CPU only", "See ``docs/missing/never-exists.md``."),
    )
    write(tmp_path, "docs/evidence.md")
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/present.rst",
        validation_page("CPU only", "See ``docs/evidence.md``."),
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert (
        "evidence path 'docs/missing/never-exists.md' does not exist" in result.stdout
    )
    assert "present.rst" not in result.stdout


def test_evidence_paths_outside_the_repository_are_skipped(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/external.rst",
        validation_page(
            "CPU only",
            "See ~/runs/out.json, /mnt/public/runs/out.json, and "
            "``output_dir/run.json``.",
        ),
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_validation_pages_require_language_counterpart(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/english_only.rst",
        validation_page(),
    )
    write(
        tmp_path,
        "docs/source-zh/rst_source/simulators/other.rst",
        validation_page("仅 CPU", "已运行。"),
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
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/demo.rst",
        validation_page(),
    )
    write(
        tmp_path,
        "docs/source-zh/rst_source/simulators/demo.rst",
        validation_page("未验证", "未运行。"),
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "validation statuses differ from the Chinese counterpart" in result.stdout


def test_subset_check_loads_the_paired_page(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/demo.rst",
        validation_page(),
    )
    write(
        tmp_path,
        "docs/source-zh/rst_source/simulators/demo.rst",
        validation_page("仅 CPU", "已运行。"),
    )

    result = run(tmp_path, "docs/source-en/rst_source/simulators/demo.rst")

    assert result.returncode == 0, result.stdout


def test_subset_check_ignores_unselected_files(tmp_path: Path) -> None:
    write(tmp_path, "docs/page.md", "[ok](other.md)\n")
    write(tmp_path, "docs/other.md", "# Other\n")
    write(tmp_path, "docs/broken.md", "[bad](missing.md)\n")

    result = run(tmp_path, "docs/page.md")

    assert result.returncode == 0, result.stdout
    assert "broken.md" not in result.stdout


def test_historical_result_is_a_validation_status(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/source-en/rst_source/simulators/demo.rst",
        validation_page("Historical result", "Recorded on a frozen snapshot."),
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


def test_design_status_applies_to_summary_documents(tmp_path: Path) -> None:
    write(tmp_path, "docs/design/a_global.md", "# Global\n")
    write(tmp_path, "docs/design/a_notes.md", "# Notes\n")

    result = run(tmp_path)

    assert result.returncode == 1
    assert "docs/design/a_global.md:1: missing design status line" in result.stdout
    assert "a_notes.md" not in result.stdout


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


def test_ignore_marker_requires_an_expiry_date(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[planned](not-yet.md) <!-- docs-check: ignore: planned later -->\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "docs-check exception has no 'until YYYY-MM-DD' date" in result.stdout


def test_expired_ignore_marker_is_an_error(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[planned](not-yet.md) "
        "<!-- docs-check: ignore until 2000-01-01: planned later -->\n",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "docs-check exception expired on 2000-01-01" in result.stdout


def test_unexpired_ignore_marker_hides_the_line(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.md",
        "[planned](not-yet.md) "
        "<!-- docs-check: ignore until 2999-12-31: planned later -->\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "not-yet.md" not in result.stdout


def test_ignore_marker_applies_to_the_next_line(tmp_path: Path) -> None:
    write(
        tmp_path,
        "docs/page.rst",
        "Page\n====\n\n"
        ".. docs-check: ignore until 2999-12-31: example command\n"
        "\n"
        "See :doc:`missing`.\n",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout


def test_valid_repository_is_clean(tmp_path: Path) -> None:
    write(tmp_path, "docs/README.md", "[page](page.md)\n")
    write(tmp_path, "docs/page.md", "# Page\n")

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "2 file(s) checked" in result.stdout
