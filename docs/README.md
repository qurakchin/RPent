# RPent Documentation

RPent's documentation is built with Sphinx. English and Simplified Chinese
sources live in parallel trees so local builds and Read the Docs use the same
layout.

## Set up the environment

From the repository root:

```bash
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
uv venv --python 3.11 .docs-venv
source .docs-venv/bin/activate
uv pip install -r docs/requirements.txt
```

The locale variables should be set in each new terminal used to build the
documentation. The Python version matches the Read the Docs build environment.

## Build and preview

Run the live-reloading English preview:

```bash
cd docs
bash autobuild.sh
```

For the Chinese documentation:

```bash
cd docs
bash autobuild.sh zh
```

Both commands serve the generated site at <http://localhost:8000> and rebuild
it when a source file changes.

If port 8000 is already in use, pass another port or use `0` to select a free
port automatically:

```bash
bash autobuild.sh zh 8001
bash autobuild.sh zh 0
```

To build without starting the preview server:

```bash
cd docs
sphinx-build -W --keep-going source-en build/html-en
sphinx-build -W --keep-going source-zh build/html-zh
```

You can also use Make:

```bash
cd docs
make html LANG=en
make html LANG=zh
```

## Clean generated files

```bash
cd docs
make clean
```

The generated `docs/build/` directory and `.docs-venv/` environment are not
tracked by Git.

## Write documentation

Follow [STYLE_GUIDE.md](STYLE_GUIDE.md) for page ownership, bilingual writing,
terminology, formatting, and review requirements.

Documentation pages use reStructuredText (RST). Keep English and Chinese pages
at matching relative paths so the language switcher can open the same page in
the other language.

- English: `source-en/rst_source/`
- Chinese: `source-zh/rst_source/`
- RST syntax reference: <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>

## Design documents

The refactor design series lives in [design/](design/README.md) as plain
Markdown outside the Sphinx trees. It explains why a change is needed and how
it will be accepted; the pages under `source-en/` and `source-zh/` describe
current behavior. Each design document starts with a status line, and
implemented phases are rewritten to match the repository in the pull request
that lands them.

## Check links and status tables

[`scripts/check_docs.py`](../scripts/check_docs.py) verifies repository-relative
Markdown links and images, same-file heading anchors, the Validation Status
tables on simulator and robot pages, and the status lines of design documents.
It runs as the `docs-check` pre-commit hook on the changed pages and fails on a
broken reference. Run the full check with:

```bash
python scripts/check_docs.py
```

RST directives and cross-references are not duplicated in the checker: both
documentation trees build in Read the Docs with `fail_on_warning: true`, so
Sphinx decides `:doc:`, `:ref:`, `include`, and directive paths.

## Release

The release checklist is [releasing.md](releasing.md). It covers version and
tag alignment, build artifacts, installation checks, explicit publishing, and
post-release verification.
