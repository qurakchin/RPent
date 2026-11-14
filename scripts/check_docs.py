#!/usr/bin/env python3
# Copyright 2026 The RPent Authors.
"""Check documentation references that can be decided offline.

The check covers only rules that the repository owns:

- repository-relative Markdown links, images, reference-style links, link
  definitions, and same-file heading anchors. Cross-file anchors are reported
  as warnings because the GitHub slug algorithm is approximated here;
- commands written in documentation: ``cd`` targets, ``python -m`` modules,
  script paths, optional-dependency names, and ``-r``/``--requirement`` files.
  Design documents under ``docs/design/`` are skipped, because they name
  modules and paths that do not exist yet;
- the **Validation Status** / **验证状态** table on simulator and real-world
  robot pages: section presence and position, evidence-level vocabulary, an
  Evidence column with the minimum content for each status, repository paths
  cited by evidence, paired English or Chinese pages, their status sequences,
  and the result numbers they report;
- the status line of each design document and the presence of its baseline
  commit (skipped with a warning when the checkout has no full history).

RST structure is not parsed here. The ``Docs`` workflow builds both trees with
``sphinx-build -W`` (``.github/workflows/docs.yml``), so Sphinx decides
directives, ``:doc:``, ``:ref:``, and other RST references. External URLs are
not fetched.

Markers use ``docs-check: ignore until YYYY-MM-DD: reason``. The marker hides
its own line and, when it is a standalone comment, the next non-blank line.
The expiry date is required; an expired marker is an error, so a documented
exception cannot outlive the reason it was written for.

Exit status is 1 when a reference, documented command, or evidence path does
not resolve, a required status table is missing or uses an unknown status word,
a row lacks the evidence its status promises, paired pages disagree, an
exception expired, or a design document has no reachable status line.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote

SUFFIXES = {".md", ".rst"}
SKIP_PARTS = {
    ".git",
    ".venv",
    ".docs-venv",
    ".reproduce",
    ".review-kit",
    "build",
    "node_modules",
}
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
MARKDOWN_LINK = re.compile(
    r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)
MARKDOWN_DEFINITION = re.compile(
    r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$"
)
MARKDOWN_REFERENCE = re.compile(r"!?\[([^\]]*)\]\[([^\]]*)\]")
IGNORE = "docs-check: ignore"
IGNORE_EXPIRY = re.compile(r"docs-check:\s*ignore\b.*?\buntil\s+(\d{4}-\d{2}-\d{2})")
TRAILING = ".,;:)]}'\"`"
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
COMMAND = re.compile(
    r"(?:^|[\s`'\"(])(bash|sh|pytest|python3?|sphinx-build)\s+([^\n`'\"]+)"
)
PIP_EXTRA = re.compile(
    r"(?:(?:uv|python3?\s+-m)\s+)?pip3?\s+install[^\n]*?"
    r"(?:-e\s+[\"']?\.\[([^\]]+)\]|\.\[([^\]]+)\])"
)
SYNC_EXTRA = re.compile(r"uv\s+sync[^\n]*?--extra(?:=|\s+)([A-Za-z0-9_-]+)")
PATH_OPTION = re.compile(
    r"--(?:override|requirement|requirements)(?:=|\s+)([^\s`'\"]+)|-r\s+([^\s`'\"]+)"
)
MODULE_OPTION = re.compile(r"-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
PLACEHOLDERS = set("<>{}*?$|")
VALIDATION_HEADINGS = {"Validation Status": "en", "验证状态": "zh"}
EVIDENCE_STATUSES = {
    "en": {
        "Verified (multiple)",
        "Verified (single)",
        "External result",
        "Historical result",
        "CPU only",
        "Unverified",
        "Not applicable",
    },
    "zh": {
        "已验证（多次）",
        "已验证（单次）",
        "外部结果",
        "历史结果",
        "仅 CPU",
        "未验证",
        "不适用",
    },
}
STABILITY_TAGS = {"Experimental", "实验性"}
STABILITY_SUFFIX = re.compile(r"^(.*?)\s*[（(]\s*(Experimental|实验性)\s*[)）]\s*$")
STATUS_KEYS = {
    "Verified (multiple)": "verified-multiple",
    "已验证（多次）": "verified-multiple",
    "Verified (single)": "verified-single",
    "已验证（单次）": "verified-single",
    "External result": "external",
    "外部结果": "external",
    "Historical result": "historical",
    "历史结果": "historical",
    "CPU only": "cpu",
    "仅 CPU": "cpu",
    "Unverified": "unverified",
    "未验证": "unverified",
    "Not applicable": "not-applicable",
    "不适用": "not-applicable",
}
EVIDENCE_PATH = re.compile(r"(?<![\w:/.-])((?:[\w.@+-]+/)+[\w.@+-]+\.[A-Za-z0-9]+)")
EVIDENCE_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
EVIDENCE_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
BACKTICK = re.compile(r"``([^`]+)``|`([^`]+)`")
RESULT_NUMBER = re.compile(r"\b\d+/\d+\b|\b\d+(?:\.\d+)?%")
COMMAND_HINTS = (
    "rpent",
    "python",
    "pytest",
    "bash",
    "sh ",
    "sphinx-build",
    "uv ",
    "git ",
    "pip ",
    "scripts/",
)
EXTERNAL_CITATION = re.compile(
    r"https?://|\bdoi\b|doi\.org|\bpaper\b|\btable\b|\breport\b|\bpublish|论文|文献|报告",
    re.IGNORECASE,
)
EXTERNAL_NOT_REPRODUCED = re.compile(
    r"not reproduc|does not record|no reproduction|未复现|没有记录|未记录",
    re.IGNORECASE,
)
SNAPSHOT = re.compile(r"snapshot|frozen|快照|冻结|commit|revision|版本", re.IGNORECASE)
LOCATOR_STATUSES = {"verified-multiple", "verified-single", "historical", "cpu"}
EXTERNAL_STATUSES = {"external"}
SNAPSHOT_STATUSES = {"historical"}
VALIDATION_PAGE_DIRS = {"simulators", "real_world_robots"}
STATUS_COLUMNS = {"Status", "状态"}
EVIDENCE_COLUMNS = {"Evidence", "证据"}
DESIGN_STATUS = re.compile(
    r"^>\s*状态：(草案|部分实施|已实施)"
    r".*?基线\s*`([0-9a-f]{7,40})`"
    r".*?最后更新\s*(\d{4}-\d{2}-\d{2})\s*$"
)
DESIGN_NAME = re.compile(r"^a_(?:\d+_[^/]+|global|summary)\.md$")


@dataclass
class Report:
    """Collected problems, warnings, and files inspected."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files: int = 0

    def _format(self, path: Path, line: int, message: str, root: Path) -> str:
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        return f"{shown}:{line}: {message}"

    def error(self, path: Path, line: int, message: str, root: Path) -> None:
        """Record one problem relative to the repository root."""
        self.errors.append(self._format(path, line, message, root))

    def warning(self, path: Path, line: int, message: str, root: Path) -> None:
        """Record one item that a person still has to decide."""
        self.warnings.append(self._format(path, line, message, root))


def repository_files(root: Path) -> list[Path]:
    """Return Markdown and RST files tracked by Git or not ignored."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        candidates = root.rglob("*")
    else:
        candidates = (
            root / name
            for name in result.stdout.decode("utf-8", "replace").split("\0")
            if name
        )
    files = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        files.append(path)
    return sorted(files)


def exact_exists(root: Path, path: Path) -> bool:
    """Check a path component by component so case must match on every host."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return path.exists()
    current = root
    for part in relative.parts:
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def has_scheme(target: str) -> bool:
    """Return whether a link target names a URL or another scheme."""
    return bool(SCHEME.match(target) or target.startswith("//"))


def split_target(target: str) -> tuple[str, str]:
    """Split a link target into path and fragment."""
    path, _, fragment = target.partition("#")
    return path, fragment


def markdown_slugs(path: Path) -> set[str]:
    """Return GitHub-style heading anchors for a Markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    seen: dict[str, int] = {}
    slugs: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if not match:
            continue
        slug = heading_slug(match.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    return slugs


def heading_slug(text: str) -> str:
    """Approximate the anchor GitHub generates for a heading."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text)


class Checker:
    """Resolve references for one repository root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.report = Report()
        self._slugs: dict[Path, set[str]] = {}
        self._ignored: set[int] = set()
        self._validation_rows: dict[Path, tuple[int, list[str]]] = {}
        self._has_en = (self.root / "docs/source-en").is_dir()
        self._has_zh = (self.root / "docs/source-zh").is_dir()
        self._warned_history = False
        self._top_level = {entry.name for entry in self.root.iterdir()}
        self._module_roots = self._load_module_roots()
        self._extras = self._load_extras()
        self._project_name = self._load_project_name()
        self._shallow = self._is_shallow()

    def _load_module_roots(self) -> set[str]:
        """Return top-level packages whose ``python -m`` names can be checked."""
        return {
            entry.name
            for entry in self.root.iterdir()
            if entry.is_dir() and (entry / "__init__.py").is_file()
        }

    def _load_extras(self) -> set[str] | None:
        """Return optional-dependency names, or None when unavailable.

        Transitional: a_1 replaces the generated extras with ``rpent-env``
        profiles; this check is replaced by the install-command rule then.
        """
        path = self.root / "pyproject.toml"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        marker = "[project.optional-dependencies]"
        if marker not in text:
            return None
        section = text.split(marker, 1)[1]
        section = re.split(r"(?m)^\[", section, maxsplit=1)[0]
        names = set(re.findall(r"(?m)^([A-Za-z0-9_-]+)\s*=\s*\[", section))
        return names or None

    def _load_project_name(self) -> str | None:
        """Return the project name used for the clone directory in examples."""
        path = self.root / "pyproject.toml"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(r"(?m)^\s*name\s*=\s*[\"']([^\"']+)[\"']", text)
        return match.group(1) if match else None

    def _is_shallow(self) -> bool:
        """Return whether the checkout lacks the history a baseline needs."""
        if not (self.root / ".git").exists():
            return False
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--is-shallow-repository"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def with_counterparts(self, files: list[Path]) -> list[Path]:
        """Add paired validation pages so subset checks can compare them."""
        selected = list(files)
        seen = set(selected)
        for path in files:
            if path.suffix.lower() != ".rst" or not self._is_validation_page(path):
                continue
            counterpart = self._language_counterpart(path)
            if counterpart is not None and counterpart.is_file():
                if counterpart not in seen:
                    selected.append(counterpart)
                    seen.add(counterpart)
        return selected

    def check(self, files: list[Path]) -> Report:
        """Check every file and return the collected report."""
        for path in files:
            self.report.files += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            self._ignored = self._ignored_lines(path, text)
            if path.suffix.lower() == ".md":
                self._check_markdown(path, text)
                self._check_design_status(path, text)
            else:
                self._check_validation_status(path, text)
            if self._checks_commands(path):
                self._check_commands(path, text)
                self._check_inline_commands(path, text)
        self._check_validation_pairs()
        return self.report

    def _checks_commands(self, path: Path) -> bool:
        """Return whether this document's commands must resolve.

        Design documents describe the target state, so they name modules and
        paths that do not exist yet. Their Markdown links and status lines are
        still checked.
        """
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return True
        return not (len(parts) >= 2 and parts[0] == "docs" and parts[1] == "design")

    def _ignored_lines(self, path: Path, text: str) -> set[int]:
        """Return line numbers hidden by ``docs-check: ignore`` markers.

        A marker on its own comment line hides the next non-blank line, so an
        RST comment can be followed by the required blank line. A marker
        appended to content hides only that line. Every marker must carry an
        ``until YYYY-MM-DD`` date; an expired marker and an invalid date are
        errors, and a missing date is a warning.
        """
        lines = text.splitlines()
        ignored: set[int] = set()
        for index, line in enumerate(lines):
            if IGNORE not in line:
                continue
            self._check_ignore_expiry(path, index + 1, line)
            ignored.add(index + 1)
            stripped = line.strip()
            if not stripped.startswith(("..", "<!--")):
                continue
            following = index + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines):
                ignored.add(following + 1)
        return ignored

    def _check_ignore_expiry(self, path: Path, line: int, text: str) -> None:
        """Require an unexpired ``until`` date on every exception marker."""
        match = IGNORE_EXPIRY.search(text)
        if match is None:
            self.report.warning(
                path,
                line,
                "docs-check exception has no 'until YYYY-MM-DD' date",
                self.root,
            )
            return
        try:
            until = date.fromisoformat(match.group(1))
        except ValueError:
            self.report.error(
                path,
                line,
                f"invalid docs-check exception date {match.group(1)!r}",
                self.root,
            )
            return
        if until < date.today():
            self.report.error(
                path,
                line,
                f"docs-check exception expired on {until.isoformat()}",
                self.root,
            )

    # Markdown ---------------------------------------------------------

    def _check_markdown(self, path: Path, text: str) -> None:
        lines = text.splitlines()
        definitions: dict[str, tuple[int, str]] = {}
        for number, line in enumerate(lines, 1):
            if number in self._ignored:
                continue
            definition = MARKDOWN_DEFINITION.match(line)
            if definition:
                definitions[definition.group(1).lower()] = (number, definition.group(2))
        for number, target in definitions.values():
            self._check_markdown_target(path, number, target)
        for number, line in enumerate(lines, 1):
            if number in self._ignored:
                continue
            visible = re.sub(r"`[^`]*`", "", line)
            for match in MARKDOWN_LINK.finditer(visible):
                self._check_markdown_target(path, number, match.group(1))
            for match in MARKDOWN_REFERENCE.finditer(visible):
                label = match.group(2) or match.group(1)
                if label.lower() not in definitions:
                    self.report.error(
                        path,
                        number,
                        f"missing Markdown link definition [{label}]",
                        self.root,
                    )

    def _check_markdown_target(self, path: Path, line: int, target: str) -> None:
        target = unquote(target.strip())
        if not target or has_scheme(target) or target.startswith("/"):
            return
        destination, fragment = split_target(target)
        if not destination:
            resolved = path
        else:
            resolved = (path.parent / destination).resolve()
        if not exact_exists(self.root, resolved):
            self.report.error(path, line, f"broken link target {target!r}", self.root)
            return
        if fragment and resolved.suffix.lower() == ".md" and resolved.is_file():
            slugs = self._slugs.setdefault(resolved, markdown_slugs(resolved))
            if fragment.lower() in slugs:
                return
            if resolved == path.resolve():
                self.report.error(
                    path,
                    line,
                    f"missing heading anchor #{fragment} in {destination or path.name}",
                    self.root,
                )
            else:
                self.report.warning(
                    path,
                    line,
                    f"heading anchor #{fragment} not found in {destination} "
                    "(slug approximation; confirm the rendered page)",
                    self.root,
                )

    def _check_design_status(self, path: Path, text: str) -> None:
        """Check the status line and reachable baseline of a design document."""
        if path.parent.name != "design" or not DESIGN_NAME.match(path.name):
            return
        match = None
        number = 1
        for number, line in enumerate(text.splitlines(), 1):
            match = DESIGN_STATUS.match(line)
            if match:
                break
        if match is None:
            self.report.error(
                path,
                1,
                "missing design status line (状态 / 基线 / 最后更新)",
                self.root,
            )
            return
        try:
            date.fromisoformat(match.group(3))
        except ValueError:
            self.report.error(
                path, number, f"invalid status date {match.group(3)!r}", self.root
            )
        baseline = match.group(2)
        if not (self.root / ".git").exists():
            self._warn_unchecked_history(path, number, "no Git history")
            return
        if self._shallow:
            self._warn_unchecked_history(path, number, "shallow checkout")
            return
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "cat-file",
                "-e",
                f"{baseline}^{{commit}}",
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            self.report.error(
                path,
                number,
                f"baseline commit {baseline!r} is not in this repository",
                self.root,
            )

    def _warn_unchecked_history(self, path: Path, line: int, reason: str) -> None:
        """Warn once when the checkout cannot resolve baseline commits."""
        if self._warned_history:
            return
        self._warned_history = True
        self.report.warning(
            path,
            line,
            f"{reason}: design baseline commits were not checked",
            self.root,
        )

    # Validation Status ------------------------------------------------

    def _is_validation_page(self, path: Path) -> bool:
        """Return whether a page must end with a Validation Status section."""
        parts = path.parts
        if "rst_source" not in parts:
            return False
        index = parts.index("rst_source")
        if len(parts) <= index + 2 or parts[index + 1] not in VALIDATION_PAGE_DIRS:
            return False
        return path.name != "index.rst"

    def _validation_language(self, path: Path) -> str | None:
        if "source-zh" in path.parts:
            return "zh"
        if "source-en" in path.parts:
            return "en"
        return None

    def _check_validation_status(self, path: Path, text: str) -> None:
        """Check the status table on simulator and real-world robot pages."""
        if not self._is_validation_page(path):
            return
        language = self._validation_language(path)
        if language is None:
            return
        lines = text.splitlines()
        heading: int | None = None
        for number, line in enumerate(lines):
            if line.strip() not in VALIDATION_HEADINGS:
                continue
            if number + 1 >= len(lines):
                continue
            underline = lines[number + 1].strip()
            if underline and set(underline) <= set("-=") and len(underline) >= 3:
                heading = number
                break
        if heading is None:
            self.report.error(
                path,
                1,
                "missing Validation Status / 验证状态 section",
                self.root,
            )
            return
        for number in range(heading + 2, len(lines) - 1):
            underline = lines[number + 1].strip()
            if (
                lines[number]
                and not lines[number][0].isspace()
                and underline
                and set(underline) <= set("-=~")
                and len(underline) >= 3
            ):
                self.report.error(
                    path,
                    number + 1,
                    "Validation Status must be the last section",
                    self.root,
                )
                break
        rows = self._list_table_rows(lines[heading + 2 :], heading + 3)
        if len(rows) < 2:
            self.report.error(
                path,
                heading + 1,
                "Validation Status section has no list-table with rows",
                self.root,
            )
            return
        header = rows[0][1]
        status_column = next(
            (i for i, cell in enumerate(header) if cell in STATUS_COLUMNS), None
        )
        evidence_column = next(
            (i for i, cell in enumerate(header) if cell in EVIDENCE_COLUMNS), None
        )
        if status_column is None:
            self.report.error(
                path,
                heading + 1,
                "Validation Status table has no Status / 状态 column",
                self.root,
            )
            return
        if evidence_column is None:
            self.report.error(
                path,
                heading + 1,
                "Validation Status table has no Evidence / 证据 column",
                self.root,
            )
            return
        allowed = EVIDENCE_STATUSES[language]
        collected: list[tuple[int, str, str]] = []
        for number, cells in rows[1:]:
            status = cells[status_column] if status_column < len(cells) else ""
            if not status:
                self.report.error(
                    path, number, "validation row has no status", self.root
                )
                continue
            base = self._evidence_status(status)
            if base is None:
                self.report.error(
                    path, number, f"unknown validation status {status!r}", self.root
                )
            elif base not in allowed:
                self.report.error(
                    path, number, f"unknown validation status {base!r}", self.root
                )
            evidence = cells[evidence_column] if evidence_column < len(cells) else ""
            if not evidence:
                self.report.error(
                    path,
                    number,
                    f"validation row {status!r} has no evidence",
                    self.root,
                )
            else:
                self._check_evidence_paths(path, number, evidence)
                if base is not None:
                    self._check_evidence_content(path, number, base, evidence)
            collected.append((number, base or status, evidence))
        self._validation_rows[path] = (heading + 1, collected)

    def _check_evidence_content(
        self, path: Path, line: int, status: str, evidence: str
    ) -> None:
        """Require the evidence shape that each status promises."""
        if line in self._ignored:
            return
        key = STATUS_KEYS.get(status)
        if key is None:
            return
        if key in LOCATOR_STATUSES and not self._has_locator(evidence):
            self.report.error(
                path,
                line,
                f"validation row {status!r} needs a locator: a command, "
                "repository path, commit, or date",
                self.root,
            )
            return
        if key in SNAPSHOT_STATUSES and not SNAPSHOT.search(evidence):
            self.report.error(
                path,
                line,
                f"validation row {status!r} must name the frozen snapshot or "
                "the commit it was measured at",
                self.root,
            )
        if key in EXTERNAL_STATUSES:
            if not EXTERNAL_CITATION.search(evidence):
                self.report.error(
                    path,
                    line,
                    f"validation row {status!r} must cite the published source",
                    self.root,
                )
            if not EXTERNAL_NOT_REPRODUCED.search(evidence):
                self.report.error(
                    path,
                    line,
                    f"validation row {status!r} must say that this repository "
                    "has not reproduced the result",
                    self.root,
                )

    @staticmethod
    def _has_locator(evidence: str) -> bool:
        """Return whether evidence names a command, path, commit, or date."""
        if EVIDENCE_DATE.search(evidence) or EVIDENCE_SHA.search(evidence):
            return True
        if EVIDENCE_PATH.search(evidence):
            return True
        for match in BACKTICK.finditer(evidence):
            span = (match.group(1) or match.group(2)).strip()
            if "/" in span or any(hint in span.lower() for hint in COMMAND_HINTS):
                return True
        return False

    @staticmethod
    def _evidence_status(status: str) -> str | None:
        """Split an optional ``(Experimental)`` stability tag from a status."""
        match = STABILITY_SUFFIX.match(status)
        if match:
            return match.group(1).strip()
        if status in STABILITY_TAGS:
            return None
        return status

    def _check_evidence_paths(self, path: Path, line: int, evidence: str) -> None:
        """Reject evidence that names an in-repository path that does not exist.

        A repository path that cannot resolve makes the row unverifiable.
        Paths outside the repository (absolute paths, ``~``, variables, or
        directories that are not top-level entries here) are left to the
        reviewer: artifacts live outside the source tree (a_3 4.5). Backticked
        directory paths are checked too, because evidence may name a directory
        instead of a file.
        """
        if line in self._ignored:
            return
        for match in EVIDENCE_PATH.finditer(evidence):
            if match.start() > 0 and evidence[match.start() - 1] == "/":
                continue
            target = match.group(1).rstrip(TRAILING)
            if self._evidence_path_exists(path, target):
                continue
            self.report.error(
                path, line, f"evidence path {target!r} does not exist", self.root
            )
        for match in BACKTICK.finditer(evidence):
            target = (match.group(1) or match.group(2)).strip().rstrip(TRAILING)
            if not target or " " in target or "/" not in target:
                continue
            if "." in target.rsplit("/", 1)[-1]:
                continue  # file paths are handled above
            if self._evidence_path_exists(path, target):
                continue
            self.report.error(
                path, line, f"evidence path {target!r} does not exist", self.root
            )

    def _evidence_path_exists(self, path: Path, target: str) -> bool:
        """Return whether a repository path is out of scope or exists."""
        if not target or has_scheme(target) or target.startswith(("www.", "~", "$")):
            return True
        if target.split("/", 1)[0] not in self._top_level:
            return True
        candidates = (self.root / target, path.parent / target)
        return any(
            exact_exists(self.root, candidate.resolve()) or candidate.resolve().is_dir()
            for candidate in candidates
        )

    def _check_validation_pairs(self) -> None:
        """Require paired pages and equivalent status sequences per language."""
        for path, (line, rows) in sorted(self._validation_rows.items()):
            if "source-en" in path.parts:
                if not self._has_zh:
                    continue
                language = "Chinese"
            elif "source-zh" in path.parts:
                if not self._has_en:
                    continue
                language = "English"
            else:
                continue
            counterpart = self._language_counterpart(path)
            if counterpart is None:
                continue
            if not exact_exists(self.root, counterpart):
                shown = counterpart.relative_to(self.root)
                self.report.error(
                    path,
                    line,
                    f"missing {language} counterpart {str(shown)!r}",
                    self.root,
                )
                continue
            if language != "Chinese":
                continue
            other = self._validation_rows.get(counterpart)
            if other is None:
                continue
            mine_keys = [STATUS_KEYS.get(status, status) for _, status, _ in rows]
            other_keys = [STATUS_KEYS.get(status, status) for _, status, _ in other[1]]
            if mine_keys != other_keys:
                self.report.error(
                    path,
                    line,
                    f"validation statuses differ from the {language} counterpart "
                    f"({[status for _, status, _ in rows]!r} != "
                    f"{[status for _, status, _ in other[1]]!r})",
                    self.root,
                )
                continue
            for (number, _, evidence), (_, _, counterpart_evidence) in zip(
                rows, other[1]
            ):
                mine = self._result_numbers(evidence)
                theirs = self._result_numbers(counterpart_evidence)
                if mine == theirs:
                    continue
                if IGNORE in evidence or IGNORE in counterpart_evidence:
                    continue
                self.report.error(
                    path,
                    number,
                    f"result numbers differ from the {language} counterpart "
                    f"({sorted(mine)} != {sorted(theirs)})",
                    self.root,
                )

    @staticmethod
    def _result_numbers(evidence: str) -> set[str]:
        """Return the ratios and percentages that both languages must share."""
        cleaned = BACKTICK.sub(" ", evidence)
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        cleaned = EVIDENCE_DATE.sub(" ", cleaned)
        return {match.group(0) for match in RESULT_NUMBER.finditer(cleaned)}

    def _language_counterpart(self, path: Path) -> Path | None:
        parts = list(path.relative_to(self.root).parts)
        for index, part in enumerate(parts):
            if part == "source-en":
                parts[index] = "source-zh"
                return self.root / Path(*parts)
            if part == "source-zh":
                parts[index] = "source-en"
                return self.root / Path(*parts)
        return None

    @staticmethod
    def _list_table_rows(
        lines: list[str], first_line: int
    ) -> list[tuple[int, list[str]]]:
        """Parse an RST list-table into ``(line number, cells)`` rows."""
        rows: list[tuple[int, list[str]]] = []
        cells: list[str] | None = None
        row_line = 0
        for offset, line in enumerate(lines):
            start = re.match(r"^\s*\* - (.*)$", line)
            if start:
                if cells is not None:
                    rows.append((row_line, cells))
                cells = [start.group(1).strip()]
                row_line = first_line + offset
                continue
            cell = re.match(r"^\s+-\s?(.*)$", line)
            if cell and cells is not None:
                cells.append(cell.group(1).strip())
                continue
            if cells is not None and line.strip() and not line[:1].isspace():
                break
        if cells is not None:
            rows.append((row_line, cells))
        return rows

    # Commands ---------------------------------------------------------------

    def _check_commands(self, path: Path, text: str) -> None:
        """Check repository paths and names named by documented commands."""
        cwd = self.root
        external = False
        block = -1
        for block_id, number, line in self._code_lines(path, text):
            if block_id != block:
                block = block_id
                cwd = self.root
                external = False
            if number in self._ignored:
                continue
            cd = re.match(r"^\s*(?:\$ )?cd\s+([^\s;&|]+)", line)
            if cd:
                cwd, external = self._apply_cd(path, number, cd.group(1), cwd)
            if external:
                continue
            self._check_command_text(path, number, line, cwd)

    def _apply_cd(
        self, path: Path, line: int, raw: str, cwd: Path
    ) -> tuple[Path, bool]:
        """Update the working directory for a documented ``cd`` command."""
        target = raw.strip(TRAILING)
        if (
            not target
            or has_scheme(target)
            or target.startswith(("~", "$", "@"))
            or PLACEHOLDERS.intersection(target)
            or "..." in target
        ):
            return cwd, True
        if target.startswith("/"):
            absolute = Path(target).resolve()
            if absolute.is_relative_to(self.root):
                return absolute, False
            return cwd, True
        if (
            self._project_name is not None
            and target.lower() == self._project_name.lower()
        ):
            # Documentation clones the repository and runs ``cd RPent``; the
            # directory is the checkout root, not a subdirectory of this tree.
            return self.root, False
        candidate = (cwd / target).resolve()
        if not candidate.is_relative_to(self.root):
            return cwd, True
        if candidate.is_dir():
            return candidate, False
        self.report.error(
            path, line, f"documented cd target {target!r} does not exist", self.root
        )
        return cwd, True

    def _check_command_text(self, path: Path, line: int, text: str, cwd: Path) -> None:
        """Check command paths and optional extras named on one line."""
        for match in PIP_EXTRA.finditer(text):
            extras = match.group(1) or match.group(2) or ""
            self._check_extras(path, line, extras)
        for match in SYNC_EXTRA.finditer(text):
            self._check_extras(path, line, match.group(1))
        for match in PATH_OPTION.finditer(text):
            self._check_command_path(path, line, match.group(1) or match.group(2), cwd)
        for match in MODULE_OPTION.finditer(text):
            self._check_module(path, line, match.group(1))
        for match in COMMAND.finditer(text):
            command, arguments = match.group(1), match.group(2)
            if command.startswith("python"):
                self._check_python_arguments(path, line, arguments, cwd)
                continue
            self._check_command_arguments(path, line, command, arguments, cwd)

    def _check_inline_commands(self, path: Path, text: str) -> None:
        """Check commands written in inline code spans outside code blocks."""
        code_lines = {number for _, number, _ in self._code_lines(path, text)}
        for number, line in enumerate(text.splitlines(), 1):
            if number in code_lines or number in self._ignored:
                continue
            for match in INLINE_CODE.finditer(line):
                span = match.group(2).strip()
                if span:
                    self._check_command_text(path, number, span, self.root)

    def _code_lines(self, path: Path, text: str) -> list[tuple[int, int, str]]:
        """Return ``(block, line number, line)`` for code and literal blocks."""
        lines = text.splitlines()
        if path.suffix.lower() == ".md":
            return self._markdown_code_lines(lines)
        return self._rst_code_lines(lines)

    @staticmethod
    def _markdown_code_lines(lines: list[str]) -> list[tuple[int, int, str]]:
        result = []
        block = 0
        fence: str | None = None
        indented = False
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if fence is not None:
                if stripped.startswith(fence):
                    fence = None
                    continue
                result.append((block, number, line))
                continue
            if stripped.startswith(("```", "~~~")):
                fence = stripped[:3]
                block += 1
                indented = False
                continue
            if not stripped and indented:
                result.append((block, number, line))
                continue
            is_code = line[:1].isspace() and len(line) - len(line.lstrip()) >= 4
            if is_code and not indented:
                block += 1
            indented = is_code
            if is_code:
                result.append((block, number, line))
        return result

    @staticmethod
    def _rst_code_lines(lines: list[str]) -> list[tuple[int, int, str]]:
        result = []
        block = 0
        in_code = False
        for number, line in enumerate(lines, 1):
            if not line.strip() and in_code:
                result.append((block, number, line))
                continue
            is_code = line[:1].isspace() and len(line) - len(line.lstrip()) >= 3
            if is_code and not in_code:
                block += 1
            in_code = is_code
            if is_code:
                result.append((block, number, line))
        return result

    def _check_python_arguments(
        self, path: Path, line: int, arguments: str, cwd: Path
    ) -> None:
        tokens = [token.strip(TRAILING) for token in arguments.split()]
        for token in tokens:
            if token == "-m":
                return
            if token.startswith("-") or not token:
                continue
            if token.endswith(".py"):
                self._check_command_path(path, line, token, cwd)
            return

    def _check_command_arguments(
        self, path: Path, line: int, command: str, arguments: str, cwd: Path
    ) -> None:
        tokens = [token.strip(TRAILING) for token in arguments.split()]
        # sphinx-build takes a source tree followed by a generated output
        # directory; only the source tree must exist in the checkout.
        limit = 1 if command == "sphinx-build" else len(tokens)
        checked = 0
        for token in tokens:
            if token.startswith("-") or not token:
                continue
            if PLACEHOLDERS.intersection(token) or "..." in token:
                continue
            if command in {"bash", "sh", "sphinx-build"}:
                if "/" not in token and not Path(token).suffix:
                    break
            elif not (token.endswith(".py") or "/" in token):
                continue
            self._check_command_path(path, line, token, cwd)
            checked += 1
            if checked >= limit:
                break

    def _check_command_path(self, path: Path, line: int, token: str, cwd: Path) -> None:
        token = token.strip(TRAILING)
        if not token or has_scheme(token) or token.startswith(("/", "~", "$", "@")):
            return
        if PLACEHOLDERS.intersection(token) or "..." in token:
            return
        for base in (cwd, self.root, path.parent):
            candidate = (base / token).resolve()
            if exact_exists(self.root, candidate):
                return
        self.report.error(
            path, line, f"documented path {token!r} does not exist", self.root
        )

    def _check_module(self, path: Path, line: int, module: str) -> None:
        parts = module.split(".")
        if len(parts) < 2 or not all(part.isidentifier() for part in parts):
            return
        if parts[0] not in self._module_roots:
            return
        base = self.root.joinpath(*parts)
        candidates = [base.with_suffix(".py"), base / "__init__.py"]
        if not any(exact_exists(self.root, candidate) for candidate in candidates):
            self.report.error(
                path, line, f"documented module {module!r} does not exist", self.root
            )

    def _check_extras(self, path: Path, line: int, extras: str) -> None:
        if self._extras is None:
            return
        for extra in extras.split(","):
            name = extra.strip()
            if not name or PLACEHOLDERS.intersection(name) or "..." in name:
                continue
            if name not in self._extras:
                self.report.error(
                    path, line, f"unknown optional dependency {name!r}", self.root
                )


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to check, relative to the repository root. "
        "Without arguments, every tracked or untracked Markdown and RST file "
        "is checked.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root to check (default: the checkout containing this script).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the summary, warnings, and errors.",
    )
    return parser.parse_args(argv)


def selected_files(root: Path, names: list[str]) -> list[Path]:
    """Resolve command-line files, keeping only documentation documents."""
    if not names:
        return repository_files(root)
    selected = []
    seen = set()
    for name in names:
        path = Path(name)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        if path.suffix.lower() not in SUFFIXES:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        selected.append(path)
        seen.add(path)
    return sorted(selected)


def main(argv: list[str] | None = None) -> int:
    """Run the check and return a process exit status."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"check_docs: {root} is not a directory", file=sys.stderr)
        return 2
    checker = Checker(root)
    files = checker.with_counterparts(selected_files(root, args.files))
    report = checker.check(files)
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(error)
    if report.errors:
        print(f"check_docs: {len(report.errors)} problem(s) in {report.files} file(s)")
        return 1
    if not args.quiet:
        print(f"check_docs: {report.files} file(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
