# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add discoverable changelog permalinks without adding sections to the TOC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docutils import nodes

# Sphinx exposes its documentation translation helper under this name.
from sphinx.locale import _  # ruff: ignore[import-private-name]
from sphinx.transforms import SphinxTransform
from sphinx.writers.html5 import HTML5Translator

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata


class ChangelogRubricIDs(SphinxTransform):
    # Run before Locale (20), so translated titles do not change the URLs.
    default_priority = 15

    def apply(self, **kwargs: object) -> None:
        if self.env.docname != "changes":
            return

        for node in self.document.findall(nodes.rubric):
            section = node.parent
            while section is not None and not isinstance(section, nodes.section):
                section = section.parent
            if section is None:
                continue

            node["classes"].append("changelog-rubric")
            if node["ids"]:
                continue

            base_id = nodes.make_id(f"{section[0].astext()} {node.astext()}")
            anchor = base_id
            suffix = 2
            while anchor in self.document.ids:
                anchor = f"{base_id}-{suffix}"
                suffix += 1
            node["ids"].append(anchor)
            self.document.set_id(node)


def depart_rubric(translator: HTML5Translator, node: nodes.rubric) -> None:
    if "changelog-rubric" in node["classes"]:
        translator.add_permalink_ref(node, _("Link to this heading"))
    HTML5Translator.depart_rubric(translator, node)


def setup(app: Sphinx) -> ExtensionMetadata:
    app.add_transform(ChangelogRubricIDs)
    app.add_node(
        nodes.rubric,
        override=True,
        html=(HTML5Translator.visit_rubric, depart_rubric),
    )
    app.add_css_file("rubric-permalinks.css")
    return {"parallel_read_safe": True, "parallel_write_safe": True}
