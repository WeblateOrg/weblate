# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for form rendering."""

from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.safestring import SafeString


class FormRenderingTest(SimpleTestCase):
    def test_icon_help_text_escapes_title_attribute(self) -> None:
        # Safe help text must still be escaped when reused in an HTML attribute.
        field = SimpleNamespace(
            auto_id="id_fuzzy",
            field=SimpleNamespace(help_as_icon=True),
            help_text=SafeString(
                'Quote "Needs editing" and <strong>HTML help text</strong>.'
            ),
        )

        rendered = render_to_string(
            "bootstrap5/layout/help_text.html", {"field": field}
        )

        self.assertIn(
            'title="Quote &quot;Needs editing&quot; and '
            '&lt;strong&gt;HTML help text&lt;/strong&gt;."',
            rendered,
        )
        self.assertNotIn('title="Quote "Needs editing"', rendered)
        self.assertNotIn("<strong>HTML help text</strong>", rendered)
