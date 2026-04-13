# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.checks.utils import highlight_string, replace_highlighted


class HighlightTestCase(SimpleTestCase):
    def test_simple(self) -> None:
        unit = MockUnit(
            source="simple {format} string",
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}")],
        )

    def test_multi(self) -> None:
        unit = MockUnit(
            source="simple {format} %d string",
            flags="python-brace-format, python-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}"), (16, 18, "%d")],
        )

    def test_overlap(self) -> None:
        unit = MockUnit(
            source='nested <a href="{format}">string</a>',
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 26, '<a href="{format}">'), (32, 36, "</a>")],
        )

    def test_syntax(self) -> None:
        unit = MockUnit(
            source="Text with a `link <https://www.sphinx-doc.org>`_.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(unit.source, unit, highlight_syntax=True),
            [(12, 13, "`"), (18, 46, "<https://www.sphinx-doc.org>"), (46, 48, "`_")],
        )
        self.assertEqual(
            highlight_string(
                "Hello `world <https://weblate.org>`_", unit, highlight_syntax=True
            ),
            [(6, 7, "`"), (13, 34, "<https://weblate.org>"), (34, 36, "`_")],
        )
        self.assertEqual(
            highlight_string("Hello **world**", unit, highlight_syntax=True),
            [(6, 8, "**"), (13, 15, "**")],
        )
        self.assertEqual(
            highlight_string("Hello *world*", unit, highlight_syntax=True),
            [(6, 7, "*"), (12, 13, "*")],
        )

    def test_escaped_markup(self) -> None:
        unit = MockUnit(
            source="&lt;strong&gt;Not limit the amount of videos&lt;/strong&gt; new users can upload",
            flags='icu-message-format, placeholders:r"&lt;[a-z/]+&gt;", xml-text',
        )
        self.assertEqual(
            highlight_string(unit.source, unit, highlight_syntax=True),
            [
                (0, 14, "&lt;strong&gt;"),
                (44, 59, "&lt;/strong&gt;"),
            ],
        )

    def test_replace_highlighted(self) -> None:
        unit = MockUnit(
            source="simple {format} %d string",
            flags="python-brace-format, python-format",
        )
        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "simple   string",
        )
        self.assertEqual(
            replace_highlighted(
                unit.source,
                unit,
                lambda start: f"x-weblate-{start}",
            ),
            "simple x-weblate-7 x-weblate-16 string",
        )

    def test_replace_highlighted_rst_without_syntax(self) -> None:
        """Without highlight_syntax, RST inline literals are not stripped."""
        unit = MockUnit(source="``release``", flags="rst-text")
        # highlight_string with default highlight_syntax=False finds no highlights
        # for RST markup, so the source is returned unchanged.
        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "``release``",
        )

    def test_replace_highlighted_rst_with_syntax(self) -> None:
        """
        With highlight_syntax=True, RST inline literal content is stripped.

        highlight_pygments yields the inner text and surrounding backtick tokens
        as separate spans, so the translatable word inside is removed.  The
        surviving characters (the second `` ` `` of the opening marker) are
        punctuation-only and not meaningful to SameCheck.
        """
        unit = MockUnit(source="``release``", flags="rst-text")
        result = replace_highlighted(unit.source, unit, highlight_syntax=True)
        # The inner word must be gone - only punctuation may remain.
        self.assertNotIn("release", result)

    def test_replace_highlighted_rst_role_with_syntax(self) -> None:
        """With highlight_syntax=True, RST :role:`...` spans are stripped."""
        unit = MockUnit(source=":ref:`index`", flags="rst-text")
        self.assertEqual(
            replace_highlighted(unit.source, unit, highlight_syntax=True),
            "",
        )
