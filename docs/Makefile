# Minimal makefile for the RPent Sphinx documentation.

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
LANG          ?= en
SOURCEDIR     = source-$(LANG)
BUILDDIR      = build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help clean diagrams check-structure Makefile

clean:
	@rm -rf "$(BUILDDIR)"

diagrams:
	@python3 _diagrams/make_diagrams.py

check-structure:
	@python3 _checks/check_structure.py

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
