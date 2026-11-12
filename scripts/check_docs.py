#!/usr/bin/env python3
"""Check documentation links and commands that must resolve in this repository.

The check covers references that can be decided offline:

- repository-relative Markdown links and images, including Markdown headings;
- RST explicit links, ``image``/``figure``/``include``/``literalinclude`` paths;
- Sphinx ``:doc:`` targets and ``:ref:`` labels, resolved inside the tree that
  contains the referencing page;
- repository paths named by common commands such as ``bash``, ``pytest``,
  ``python -m``, and ``sphinx-build``;
- optional-dependency names used by ``uv pip install -e ".[...]"`` and
  ``uv sync --extra ...``.

External URLs are not fetched. A line containing ``docs-check: ignore`` is
skipped, so an intentional unreleased path can be documented with a reason on
the same line.

Exit status is 1 when any reference is broken.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
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
RST_LINK = re.compile(r"`[^`<>]*<([^<>]+)>`__?")
RST_DIRECTIVE = re.compile(
    r"^\s*\.\.\s+(?:image|figure|include|literalinclude)::\s*(\S+)"
)
DOC_ROLE = re.compile(r":doc:`([^`]+)`")
REF_ROLE = re.compile(r":(?:ref|numref):`([^`]+)`")
LABEL = re.compile(r"^\s*\.\.\s+_([^:]+):\s*$")
IGNORE = "docs-check: ignore"
COMMAND = re.compile(
    r"(?:^|[\s`'\"(])(bash|sh|pytest|python3?|sphinx-build)\s+([^\n`'\"]+)"
)
UV_EXTRA = re.compile(
    r"(?:uv\s+(?:pip\s+install|sync))[^\n]*?"
    r"(?:-e\s+[\"']?\.\[([^\]]+)\]|--extra(?:=|\s+)([A-Za-z0-9_-]+))"
)
PATH_OPTION = re.compile(
    r"--(?:override|requirement|requirements)(?:=|\s+)([^\s`'\"]+)|-r\s+([^\s`'\"]+)"
)
MODULE_OPTION = re.compile(r"-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
PLACEHOLDERS = set("<>{}*?$|")
TRAILING = ".,;:)]}'\"`"


@dataclass
class Report:
    """Collected problems and files inspected."""

    errors: list[str] = field(default_factory=list)
    files: int = 0

    def error(self, path: Path, line: int, message: str, root: Path) -> None:
        """Record one problem relative to the repository root."""
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        self.errors.append(f"{shown}:{line}: {message}")


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

    def check(self, files: list[Path]) -> Report:
        """Check every file and return the collected report."""
        for path in files:
            self.report.files += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() == ".md":
                self._check_markdown(path, text)
            else:
                self._check_rst(path, text)
            self._check_commands(path, text)
        return self.report

    # Markdown ---------------------------------------------------------

    def _check_markdown(self, path: Path, text: str) -> None:
        for number, line in enumerate(text.splitlines(), 1):
            if IGNORE in line:
                continue
            line = re.sub(r"`[^`]*`", "", line)
            for match in MARKDOWN_LINK.finditer(line):
                self._check_markdown_target(path, number, match.group(1))

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

    # RST --------------------------------------------------------------

    def _check_rst(self, path: Path, text: str) -> None:
        tree = self._sphinx_root(path)
        for number, line in enumerate(text.splitlines(), 1):
            if IGNORE in line:
                continue
            for match in RST_DIRECTIVE.finditer(line):
                self._check_rst_path(path, number, match.group(1))
            for match in RST_LINK.finditer(line):
                self._check_rst_link(path, number, match.group(1))
            for match in DOC_ROLE.finditer(line):
                self._check_doc_role(path, number, match.group(1), tree)
            for match in REF_ROLE.finditer(line):
                self._check_ref_role(path, number, match.group(1), tree)

    def _check_rst_path(self, path: Path, line: int, target: str) -> None:
        target = unquote(target.strip())
        if not target or has_scheme(target) or target.startswith("/"):
            return
        destination, _ = split_target(target)
        resolved = (path.parent / destination).resolve()
        if not exact_exists(self.root, resolved):
            self.report.error(path, line, f"broken RST path {target!r}", self.root)

    def _check_rst_link(self, path: Path, line: int, target: str) -> None:
        target = unquote(target.strip())
        if not target or has_scheme(target):
            return
        destination, _ = split_target(target)
        # A bare name is an RST label or an implicit section target. Only
        # path-like targets are decided here.
        if "/" not in destination and not Path(destination).suffix:
            return
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
            if IGNORE in line:
                continue
            cd = re.match(r"^\s*(?:\$ )?cd\s+([^\s;&|]+)", line)
            if cd:
                target = Path(cd.group(1).strip(TRAILING))
                candidate = (cwd / target).resolve()
                if (
                    not has_scheme(str(target))
                    and not target.is_absolute()
                    and not PLACEHOLDERS.intersection(str(target))
                    and candidate.is_dir()
                    and candidate.is_relative_to(self.root)
                ):
                    cwd = candidate
                    external = False
                else:
                    external = True
            if external:
                continue
            for match in UV_EXTRA.finditer(line):
                extras = match.group(1) or match.group(2) or ""
                self._check_extras(path, number, extras)
            for match in PATH_OPTION.finditer(line):
                self._check_command_path(
                    path, number, match.group(1) or match.group(2), cwd
                )
            for match in MODULE_OPTION.finditer(line):
                self._check_module(path, number, match.group(1))
            for match in COMMAND.finditer(line):
                command, arguments = match.group(1), match.group(2)
                if command.startswith("python"):
                    self._check_python_arguments(path, number, arguments, cwd)
                    continue
                self._check_command_arguments(path, number, command, arguments, cwd)

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
