# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Prompt bundle dataclass for robot-contributed LLM prompts.

Lives in :mod:`rpent.robots` so each robot's
``prompt_bundle.py`` (e.g. :mod:`robots.libero.prompt_bundle`)
can import it without depending on the RPC transport layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from rpent.prompt.assembly import PromptSection
from rpent.prompt.utils import PromptNode, format_prompt

PromptFactory = Callable[..., "PromptNode | Sequence[PromptSection]"]
ToolSectionsFactory = Callable[
    ..., "Sequence[PromptSection] | Mapping[str, PromptNode]"
]


@dataclass(frozen=True)
class PromptBundle:
    """Python-defined prompt factories for one robot.

    ``system`` and ``user`` are the robot's domain contribution. The shared
    assembly layer inserts base rules, run-axis contracts, tool guidance, and
    memory pointers around them. ``tool_sections`` supplies the guidance for
    the tools this slice exposes, such as native tools; it may be omitted when
    the slice adds no tool guidance. Tool schemas stay with the toolkit, so
    this text must not restate call signatures. It takes the same variables
    and must stay a pure function so ``--dump-prompt`` can render without
    starting a runtime. ``source`` is the fallback provenance; contributions
    built with :func:`rpent.prompt.assembly.sections` record their own module
    instead.
    """

    system: PromptFactory
    user: PromptFactory
    tool_sections: ToolSectionsFactory | None = None
    source: str = ""

    def render(
        self,
        variant: str,
        *,
        variables: Mapping[str, object] | None = None,
    ) -> str:
        """Render one prompt variant (``"system"`` or ``"user"``).

        This is the pre-assembly helper for callers that need one rendered
        variant. Factories that return ``PromptSection`` contributions are
        rendered with their layers by :func:`rpent.prompt.assembly.assemble_prompt`;
        passing them here is an error because the sections would lose their
        provenance.
        """
        if variant not in ("system", "user"):
            raise ValueError(f"unknown prompt variant: {variant!r}")
        node = getattr(self, variant)(variables)
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            if any(isinstance(section, PromptSection) for section in node):
                raise ValueError(
                    "PromptSection contributions are rendered by assemble_prompt, "
                    "not PromptBundle.render"
                )
        return format_prompt(node, variables=variables)
