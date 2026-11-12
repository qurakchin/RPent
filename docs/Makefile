# Minimal makefile for the RPent Sphinx documentation.

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
LANG          ?= en
SOURCEDIR     = source-$(LANG)
BUILDDIR      = build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help clean diagrams Makefile

clean:
	@rm -rf "$(BUILDDIR)"

diagrams:
	@python3 _diagrams/make_diagrams.py

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
