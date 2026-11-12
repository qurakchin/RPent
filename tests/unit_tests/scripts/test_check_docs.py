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


def test_valid_repository_is_clean(tmp_path: Path) -> None:
    write(tmp_path, "docs/README.md", "[page](page.md)\n")
    write(tmp_path, "docs/page.md", "# Page\n")

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "2 file(s) checked" in result.stdout
