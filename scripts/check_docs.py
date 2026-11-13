#!/usr/bin/env python3
# Copyright 2026 The RPent Authors.
"""Check documentation links and commands that must resolve in this repository.

The check covers references that can be decided offline:

- repository-relative Markdown links and images, including reference-style
  links, link definitions, and Markdown headings;
- RST explicit links, ``image``/``figure``/``include``/``literalinclude``
  paths (including Sphinx tree-absolute paths), and ``:download:`` roles;
- Sphinx ``:doc:`` targets and ``:ref:`` labels, resolved inside the tree that
  contains the referencing page;
- repository paths named by common commands such as ``bash``, ``pytest``,
  ``python -m``, and ``sphinx-build``, in code blocks and inline code spans;
- optional-dependency names used by ``pip install -e ".[...]"``,
  ``uv pip install``, and ``uv sync --extra ...``;
- the presence and vocabulary of the **Validation Status** table on simulator
  and real-world robot pages, the repository paths it cites, and the agreement
  of its status rows with the paired English or Chinese page;
- the status line of each design document and the presence of its baseline
  commit (skipped with a warning when the checkout has no full history).

External URLs are not fetched. A line containing ``docs-check: ignore`` is
skipped, and the following line is skipped too, so an intentional example or
unreleased path can be documented with a reason.

Exit status is 1 when any reference is broken or a required status table is
missing or uses an unknown status word.
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
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
RST_LINK = re.compile(r"`[^`<>]*<([^<>]+)>`__?")
RST_DIRECTIVE = re.compile(
    r"^\s*\.\.\s+(?:image|figure|include|literalinclude)::\s*(\S+)"
)
RST_DOWNLOAD = re.compile(r":download:`([^`]+)`")
DOC_ROLE = re.compile(r":doc:`([^`]+)`")
REF_ROLE = re.compile(r":(?:ref|numref):`([^`]+)`")
LABEL = re.compile(r"^\s*\.\.\s+_([^:]+):\s*$")
IGNORE = "docs-check: ignore"
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
TRAILING = ".,;:)]}'\"`"
VALIDATION_HEADINGS = {"Validation Status": "en", "验证状态": "zh"}
VALIDATION_STATUSES = {
    "en": {
        "Verified (multiple)",
        "Verified (single)",
        "External result",
        "Historical result",
        "CPU only",
        "Unverified",
        "Experimental",
        "Not applicable",
    },
    "zh": {
        "已验证（多次）",
        "已验证（单次）",
        "外部结果",
        "历史结果",
        "仅 CPU",
        "未验证",
        "实验性",
        "不适用",
    },
}
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
    "Experimental": "experimental",
    "实验性": "experimental",
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
        """Record one skipped check that a full checkout would decide."""
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
        self._labels: dict[Path, set[str]] = {}
        self._slugs: dict[Path, set[str]] = {}
        self._extras = self._load_extras()
        self._project_name = self._load_project_name()
        self._shallow = self._is_shallow()
        self._ignored: set[int] = set()
        self._validation_rows: dict[Path, tuple[int, list[str]]] = {}
        self._has_en = (self.root / "docs/source-en").is_dir()
        self._has_zh = (self.root / "docs/source-zh").is_dir()
        self._warned_history = False

    def _load_extras(self) -> set[str] | None:
        """Return optional-dependency names, or None when unavailable."""
        path = self.root / "pyproject.toml"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import-not-found,no-redef]
            except ImportError:
                return self._extras_from_text(text)
        try:
            data = tomllib.loads(text)
        except (ValueError, TypeError):
            return self._extras_from_text(text)
        optional = data.get("project", {}).get("optional-dependencies", {})
        return set(optional) if isinstance(optional, dict) else None

    @staticmethod
    def _extras_from_text(text: str) -> set[str] | None:
        """Parse extra names without a TOML parser."""
        marker = "[project.optional-dependencies]"
        if marker not in text:
            return None
        section = text.split(marker, 1)[1]
        section = re.split(r"(?m)^\[", section, maxsplit=1)[0]
        return set(re.findall(r"(?m)^([A-Za-z0-9_-]+)\s*=\s*\[", section))

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

    def check(self, files: list[Path]) -> Report:
        """Check every file and return the collected report."""
        for path in files:
            self.report.files += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            self._ignored = self._ignored_lines(text)
            if path.suffix.lower() == ".md":
                self._check_markdown(path, text)
                self._check_design_status(path, text)
            else:
                self._check_rst(path, text)
            self._check_commands(path, text)
            self._check_inline_commands(path, text)
        self._check_validation_pairs()
        return self.report

    @staticmethod
    def _ignored_lines(text: str) -> set[int]:
        """Return line numbers hidden by ``docs-check: ignore`` markers.

        A marker on its own comment line hides the next non-blank line, so an
        RST comment can be followed by the required blank line. A marker
        appended to content hides only that line.
        """
        lines = text.splitlines()
        ignored: set[int] = set()
        for index, line in enumerate(lines):
            if IGNORE not in line:
                continue
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
            if fragment.lower() not in slugs:
                self.report.error(
                    path,
                    line,
                    f"missing heading anchor #{fragment} in {destination or path.name}",
                    self.root,
                )

    def _check_design_status(self, path: Path, text: str) -> None:
        """Check the status line and reachable baseline of a design document."""
        if path.parent.name != "design" or not path.name.startswith("a_"):
            return
        match = None
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

    # RST --------------------------------------------------------------

    def _check_rst(self, path: Path, text: str) -> None:
        tree = self._sphinx_root(path)
        for number, line in enumerate(text.splitlines(), 1):
            if number in self._ignored:
                continue
            for match in RST_DIRECTIVE.finditer(line):
                self._check_rst_path(path, number, match.group(1), tree)
            for match in RST_DOWNLOAD.finditer(line):
                self._check_rst_path(path, number, match.group(1), tree)
            for match in RST_LINK.finditer(line):
                self._check_rst_link(path, number, match.group(1), tree)
            for match in DOC_ROLE.finditer(line):
                self._check_doc_role(path, number, match.group(1), tree)
            for match in REF_ROLE.finditer(line):
                self._check_ref_role(path, number, match.group(1), tree)
        self._check_validation_status(path, text)

    def _check_rst_path(
        self, path: Path, line: int, target: str, tree: Path | None
    ) -> None:
        target = unquote(target.strip())
        if not target or has_scheme(target):
            return
        destination, _ = split_target(target)
        if destination.startswith("/"):
            if tree is None:
                return
            resolved = (tree / destination.lstrip("/")).resolve()
        else:
            resolved = (path.parent / destination).resolve()
        if not exact_exists(self.root, resolved):
            self.report.error(path, line, f"broken RST path {target!r}", self.root)

    def _check_rst_link(
        self, path: Path, line: int, target: str, tree: Path | None
    ) -> None:
        target = unquote(target.strip())
        if not target or has_scheme(target):
            return
        destination, _ = split_target(target)
        # A bare name is an RST label or an implicit section target. Only
        # path-like targets are decided here.
        if "/" not in destination and not Path(destination).suffix:
            return
        if destination.startswith("/"):
            if tree is None:
                return
            resolved = (tree / destination.lstrip("/")).resolve()
        else:
            resolved = (path.parent / destination).resolve()
        if resolved.suffix == "":
            resolved = resolved.with_suffix(".rst")
        if not exact_exists(self.root, resolved):
            self.report.error(path, line, f"broken RST link {target!r}", self.root)

    def _check_doc_role(
        self, path: Path, line: int, target: str, tree: Path | None
    ) -> None:
        target = target.strip()
        if "<" in target and target.endswith(">"):
            target = target[target.index("<") + 1 : -1].strip()
        if has_scheme(target):
            return
        if tree is None:
            self.report.error(
                path,
                line,
                f":doc: target {target!r} is outside a Sphinx tree",
                self.root,
            )
            return
        if target.startswith("/"):
            resolved = tree / target.lstrip("/")
        else:
            resolved = path.parent / target
        resolved = resolved.resolve()
        if resolved.suffix == "":
            resolved = resolved.with_suffix(".rst")
        if not exact_exists(self.root, resolved):
            self.report.error(path, line, f"broken :doc: target {target!r}", self.root)

    def _check_ref_role(
        self, path: Path, line: int, target: str, tree: Path | None
    ) -> None:
        target = target.strip()
        if "<" in target and target.endswith(">"):
            target = target[target.index("<") + 1 : -1].strip()
        if tree is None:
            return
        labels = self._tree_labels(tree)
        if target not in labels:
            self.report.error(path, line, f"unknown :ref: label {target!r}", self.root)

    def _sphinx_root(self, path: Path) -> Path | None:
        for parent in path.parents:
            if (parent / "conf.py").is_file():
                return parent
            if parent == self.root:
                break
        return None

    def _tree_labels(self, tree: Path) -> set[str]:
        labels = self._labels.get(tree)
        if labels is not None:
            return labels
        labels = set()
        for path in tree.rglob("*.rst"):
            if any(part in SKIP_PARTS for part in path.relative_to(tree).parts):
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = LABEL.match(line)
                if match:
                    labels.add(match.group(1).strip())
        self._labels[tree] = labels
        return labels

    def _check_validation_status(self, path: Path, text: str) -> None:
        """Check the status table on simulator and real-world robot pages."""
        parts = path.parts
        if "rst_source" not in parts:
            return
        index = parts.index("rst_source")
        if len(parts) <= index + 2 or parts[index + 1] not in VALIDATION_PAGE_DIRS:
            return
        if path.name == "index.rst":
            return
        if "source-zh" in parts:
            language = "zh"
        elif "source-en" in parts:
            language = "en"
        else:
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
        allowed = VALIDATION_STATUSES[language]
        statuses: list[str] = []
        for line_number, cells in rows[1:]:
            status = cells[status_column] if status_column < len(cells) else ""
            statuses.append(status)
            if not status:
                self.report.error(
                    path, line_number, "validation row has no status", self.root
                )
                continue
            if status not in allowed:
                self.report.error(
                    path,
                    line_number,
                    f"unknown validation status {status!r}",
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

    def _check_evidence_paths(self, path: Path, line: int, evidence: str) -> None:
        """Reject evidence that names a repository path that does not exist.

        Evidence often cites an artifact or guide by path. A path that cannot
        resolve makes the row unverifiable, even when the cell is non-empty.
        """
        if line in self._ignored:
            return
        for match in EVIDENCE_PATH.finditer(evidence):
            target = match.group(1).rstrip(TRAILING)
            if has_scheme(target) or target.startswith(("www.", "~", "$")):
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

    # Commands ---------------------------------------------------------

    def _check_commands(self, path: Path, text: str) -> None:
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
            # Documentation clones the repository and then runs ``cd RPent``
            # (or the project name as spelled by the host). The directory is
            # the checkout root, not a subdirectory that must exist in the tree.
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
        for index, token in enumerate(tokens):
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
        if parts[0] not in {"rpent", "robots", "tests", "calibration_tools"}:
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
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root to check (default: the checkout containing this script).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the summary and errors.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the check and return a process exit status."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"check_docs: {root} is not a directory", file=sys.stderr)
        return 2
    files = repository_files(root)
    report = Checker(root).check(files)
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
