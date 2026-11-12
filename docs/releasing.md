# Release checklist

This checklist is for maintainers preparing a tagged RPent release. It keeps
the version, tag, build artifacts, and published package aligned. Publishing is
an explicit action: merging to `main`, running checks, or creating a local tag
does not publish anything.

## 1. Prepare the release

- [ ] Start from an up-to-date `main` with a clean working tree and green
      required CI checks.
- [ ] Choose the version and record it in `pyproject.toml` under
      `[project] version`.
- [ ] Update the release notes under
      `docs/source-en/rst_source/resources/` and the matching
      `docs/source-zh/rst_source/resources/` page. Add a new page and its
      toctree entry when the version has its own notes page. Keep the English
      and Chinese pages aligned.
- [ ] Update the README and installation guides when user-facing installation,
      supported robots, or advertised features changed.
- [ ] Confirm that every validation claim in the release notes uses the status
      wording in [STYLE_GUIDE.md](STYLE_GUIDE.md#validation-status) and names
      its scope.

Recommended version and tag format: the tag is `v<version>`, for example
`v0.2.0`, and matches the value in `pyproject.toml`.

## 2. Run the checks

- [ ] `pre-commit run --all-files`
- [ ] `pytest tests/unit_tests -v`
- [ ] `python scripts/check_docs.py`
- [ ] `sphinx-build -W --keep-going docs/source-en docs/build/html-en`
- [ ] `sphinx-build -W --keep-going docs/source-zh docs/build/html-zh`
- [ ] Run the GPU suites for the robot stacks affected by the release, using
      [run_gpu_suite.sh](../tests/e2e_tests/run_gpu_suite.sh) and fresh output
      and virtualenv directories. Record the targets, results, and output
      paths.

Record the commands and results in the release pull request. A skipped check
needs a reason and an explicit limitation.

## 3. Build and verify the artifacts

- [ ] Build from the release commit:

      ```bash
      uv build
      ```

- [ ] Inspect the file list in both the sdist and the wheel. The package must
      not include run outputs, checkpoints, credentials, or generated docs.
- [ ] Install the wheel into a fresh virtualenv and verify the entry points:

      ```bash
      uv venv --python 3.11 /tmp/rpent-release-venv
      source /tmp/rpent-release-venv/bin/activate
      uv pip install dist/rpent-<version>-py3-none-any.whl
      rpent --help
      python -c "import rpent"
      ```

- [ ] Record the artifact names and their SHA-256 hashes in the release pull
      request.

## 4. Tag and publish

- [ ] Commit the version, release notes, and documentation changes.
- [ ] Create an annotated tag on that commit and push it:

      ```bash
      git tag -a v<version> -m "RPent v<version>"
      git push upstream v<version>
      ```

- [ ] Create the GitHub Release from the tag. Attach the sdist, wheel, and
      their hashes. Use the release notes page as the description.
- [ ] Publish to PyPI only through the project's explicit release procedure
      and credentials. Do not publish from a branch or an untagged commit.
- [ ] If the release is withdrawn, yank the affected files on PyPI and state
      the reason in the GitHub Release; do not move or reuse the tag.

## 5. Verify the published package

- [ ] Install the exact released version into a fresh environment from the
      package index, not from the checkout:

      ```bash
      uv venv --python 3.11 /tmp/rpent-pypi-venv
      uv pip install --python /tmp/rpent-pypi-venv/bin/python rpent==<version>
      /tmp/rpent-pypi-venv/bin/rpent --help
      ```

- [ ] Confirm that the installed version reports the tagged version and that
      the documented quick-start command still works in its minimal
      configuration.
- [ ] Close the release pull request and announce the release with the scope
      and limitations recorded above.

## What this checklist does not do

Publishing requires a separate explicit action and credentials available only
to maintainers. The repository contains no release credentials, and no workflow
publishes on merge.
