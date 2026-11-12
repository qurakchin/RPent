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

## Single-source rules

State each fact once and link to it from other pages. The table lists where the
canonical explanation lives; when a fact changes, update the owner first, then
check the pages that link to it.

| Fact | Canonical location |
| --- | --- |
| Command-line flags, defaults, and run output | `source-{en,zh}/rst_source/guides/cli.rst` |
| Planner backends, credentials, and limits | `source-{en,zh}/rst_source/guides/configure_planner.rst` |
| Memory versions, caching, and exploration | `source-{en,zh}/rst_source/guides/memory.rst` |
| Flash plan format and replay | `source-{en,zh}/rst_source/guides/flash.rst` |
| Success signals and reproduction commands | Each page under `source-{en,zh}/rst_source/simulators/` and `real_world_robots/` |
| Reported results, sources, and denominators | `_static/leaderboard/results.json` |
| Counting and reporting conventions | `source-{en,zh}/rst_source/leaderboard/methodology.rst` |
| Execution flow and component boundaries | `source-{en,zh}/rst_source/development/architecture.rst` |

Do not restate a full explanation on a second page. Use a one-sentence summary
and a `:doc:` or `:ref:` link instead.

## Architecture diagrams

`source-{en,zh}/rst_source/development/architecture.rst` and
`source-{en,zh}/rst_source/get_started/overview.rst` use the SVG files in
`_static/img/`. Their source is `_diagrams/make_diagrams.py`:

```bash
cd docs
make diagrams
```

The script writes `architecture-{en,zh}.svg` and
`execution-flow-{en,zh}.svg`, plus their `.dot` files, and requires Graphviz
(`dot`) on `PATH`. Update the labels or edges in the script rather than editing
SVG files by hand, and keep the diagrams aligned with the code layout: do not
show robots, layers, or components that do not exist in the repository.

## Leaderboard data

`_static/leaderboard/results.json` (schema version 4) is the only source for
leaderboard pages and README charts. The `leaderboard` extension validates
references and renders the tables, notes, and Sources section at build time.

When adding a result:

- Reference an existing `source_ids` entry or add a source record with a URL,
  note, and `commit` when the record identifies a repository revision. The
  build rejects a `commit` that is not a 7–40 character lowercase hex revision.
- Set `episodes` and `successes` only when the source reports them. When only a
  rounded rate is published, set `successes_estimated: true` and let the
  extension display the derived count with `≈`.
- Use `status: "derived"` for aggregates computed from other rows, and record
  the calculation.
- Update `leaderboard/methodology.rst` if the counting rule changes.

## Before you submit

```bash
cd docs
sphinx-build -E -W --keep-going source-en build/html-en
sphinx-build -E -W --keep-going source-zh build/html-zh
git diff --check
```

English and Chinese pages must keep matching relative paths under
`rst_source/`. When a page moves or is renamed, add a redirect in both
`source-en/conf.py` and `source-zh/conf.py`. Check that local images and
`:doc:` targets resolve in both builds; warnings fail the strict build.
