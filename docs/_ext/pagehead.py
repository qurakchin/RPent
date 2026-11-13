"""Render the standard page header used by every substantive page.

A page declares who it is for, what the reader can do afterwards, when to read
it, and when to skip it::

    .. page-head::
       :for: Engineers running their first LIBERO-PRO task
       :outcome: A completed task and the artifacts that show its result
       :read-when: You are installing RPent or running a simulator task
       :skip-when: You only need flag defaults; see :doc:`../guides/cli`

The four options are required: the directive warns when one is missing, and
the documentation build treats warnings as errors. Keeping the header in one
directive makes the opening structure identical in both languages and gives
the page map below it a fixed position.
"""

from __future__ import annotations

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.statemachine import StringList
from sphinx.util import logging

LOGGER = logging.getLogger(__name__)

LABELS = {
    "en": {
        "for": "For",
        "outcome": "After reading",
        "read-when": "Read when",
        "skip-when": "Skip when",
    },
    "zh": {
        "for": "给谁",
        "outcome": "读完能做",
        "read-when": "何时读",
        "skip-when": "何时跳过",
    },
}

OPTIONS = ("for", "outcome", "read-when", "skip-when")


class PageHeadDirective(Directive):
    has_content = False
    required_arguments = 0
    optional_arguments = 0
    option_spec = {name: directives.unchanged_required for name in OPTIONS}

    def run(self):
        env = self.state.document.settings.env
        language = env.config.language if env.config.language in LABELS else "en"
        labels = LABELS[language]

        missing = [name for name in OPTIONS if name not in self.options]
        if missing:
            LOGGER.warning(
                "page-head is missing required option(s): %s",
                ", ".join(missing),
                location=self.state_machine.node,
            )

        container = nodes.container(classes=["rpent-page-head"])
        for name in OPTIONS:
            if name not in self.options:
                continue
            row = nodes.paragraph(classes=[f"rpent-page-head-{name}"])
            row += nodes.inline(
                text=f"{labels[name]}： " if language == "zh" else f"{labels[name]}: ",
                classes=["rpent-page-head-label"],
            )
            self.state.nested_parse(
                StringList([self.options[name]]), 0, row
            )
            container += row
        return [container]


def setup(app):
    app.add_directive("page-head", PageHeadDirective)
    return {"version": "1.0", "parallel_read_safe": True}
