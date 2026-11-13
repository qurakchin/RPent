#!/usr/bin/env python3
# Copyright 2026 The RPent Authors.
"""Check documentation references that can be decided offline.

The check covers only rules that the repository owns:

- repository-relative Markdown links, images, reference-style links, link
  definitions, and same-file heading anchors. Cross-file anchors are reported
  as warnings because the GitHub slug algorithm is approximated here;
- the **Validation Status** / **验证状态** table on simulator and real-world
  robot pages: section presence and position, evidence-level vocabulary,
  evidence cells, repository paths cited by evidence, paired English or
  Chinese pages, and agreement of their status sequences;
- the status line of each design document and the presence of its baseline
  commit (skipped with a warning when the checkout has no full history).

RST structure is not parsed here. Both documentation trees build in Read the
Docs with ``fail_on_warning: true``, so Sphinx decides directives, ``:doc:``,
``:ref:``, and other RST references. External URLs are not fetched.

Markers use ``docs-check: ignore until YYYY-MM-DD: reason``. The marker hides
its own line and, when it is a standalone comment, the next non-blank line.
The expiry date is required; an expired marker is an error, so a documented
exception cannot outlive the reason it was written for.

Exit status is 1 when a reference is broken, a required status table is
missing or uses an unknown status word, an exception expired, or a design
document has no reachable status line.
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
        self._shallow = self._is_shallow()

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
        self._check_validation_pairs()
        return self.report

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
        allowed = EVIDENCE_STATUSES[language]
        statuses: list[str] = []
        for line_number, cells in rows[1:]:
            status = cells[status_column] if status_column < len(cells) else ""
            if not status:
                self.report.error(
                    path, line_number, "validation row has no status", self.root
                )
                continue
            base = self._evidence_status(status)
            if base is None:
                self.report.error(
                    path,
                    line_number,
                    f"unknown validation status {status!r}",
                    self.root,
                )
            else:
                statuses.append(base)
                if base not in allowed:
                    self.report.error(
                        path,
                        line_number,
                        f"unknown validation status {base!r}",
                        self.root,
                    )
            if evidence_column is not None:
                evidence = (
                    cells[evidence_column] if evidence_column < len(cells) else ""
                )
                if not evidence:
                    self.report.error(
                        path,
                        line_number,
                        f"validation row {status!r} has no evidence",
                        self.root,
                    )
                else:
                    self._check_evidence_paths(path, line_number, evidence)
        self._validation_rows[path] = (heading + 1, statuses)

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
        reviewer: artifacts live outside the source tree (a_3 4.5).
        """
        if line in self._ignored:
            return
        for match in EVIDENCE_PATH.finditer(evidence):
            if match.start() > 0 and evidence[match.start() - 1] == "/":
                continue
            target = match.group(1).rstrip(TRAILING)
            if has_scheme(target) or target.startswith(("www.", "~", "$")):
                continue
            if target.split("/", 1)[0] not in self._top_level:
                continue
            candidates = (self.root / target, path.parent / target)
            if any(
                exact_exists(self.root, candidate.resolve()) for candidate in candidates
            ):
                continue
            self.report.error(
                path, line, f"evidence path {target!r} does not exist", self.root
            )

    def _check_validation_pairs(self) -> None:
        """Require paired pages and equivalent status sequences per language."""
        for path, (line, statuses) in sorted(self._validation_rows.items()):
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
            if [STATUS_KEYS.get(item, item) for item in statuses] != [
                STATUS_KEYS.get(item, item) for item in other[1]
            ]:
                self.report.error(
                    path,
                    line,
                    "validation statuses differ from the Chinese counterpart "
                    f"({statuses!r} != {other[1]!r})",
                    self.root,
                )

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
