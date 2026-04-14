# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.checks.utils import highlight_string


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
        self.assertEqual(
            highlight_string(":guilabel:`Hello`", unit, highlight_syntax=True),
            [(0, 11, ":guilabel:`"), (16, 17, "`")],
        )
        self.assertEqual(
            highlight_string(":Code:`printf()`", unit, highlight_syntax=True),
            [(0, 7, ":Code:`"), (15, 16, "`")],
        )
        self.assertEqual(
            highlight_string("`printf()`:Code:", unit, highlight_syntax=True),
            [(0, 1, "`"), (9, 16, "`:Code:")],
        )
        self.assertEqual(
            highlight_string(":file:`/tmp/example.txt`", unit, highlight_syntax=True),
            [(0, 7, ":file:`"), (23, 24, "`")],
        )
        self.assertEqual(
            highlight_string(":code:`printf()`", unit, highlight_syntax=True),
            [(0, 7, ":code:`"), (15, 16, "`")],
        )
        self.assertEqual(
            highlight_string(":math:`x + y`", unit, highlight_syntax=True),
            [(0, 7, ":math:`"), (12, 13, "`")],
        )
        self.assertEqual(
            highlight_string(":sub:`2`", unit, highlight_syntax=True),
            [(0, 6, ":sub:`"), (7, 8, "`")],
        )
        self.assertEqual(
            highlight_string(":sup:`2`", unit, highlight_syntax=True),
            [(0, 6, ":sup:`"), (7, 8, "`")],
        )
        self.assertEqual(
            highlight_string(
                ":ref:`review workflow <reviews>`", unit, highlight_syntax=True
            ),
            [(0, 6, ":ref:`"), (21, 32, " <reviews>`")],
        )
        self.assertEqual(
            highlight_string(
                "`review workflow <reviews>`:ref:",
                unit,
                highlight_syntax=True,
            ),
            [(0, 1, "`"), (16, 32, " <reviews>`:ref:")],
        )

    def test_rst_duplicate_fragment(self) -> None:
        unit = MockUnit(
            source="Use ``:ref:`foo``` syntax, then see :ref:`foo`.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(
                "Use ``:ref:`foo``` syntax, then see :ref:`foo`.",
                unit,
            ),
            [(36, 46, ":ref:`foo`")],
        )

    def test_rst_escaped_role_example(self) -> None:
        unit = MockUnit(
            source=r"Use \:ref:`foo` literally, then see :ref:`foo`.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(
                r"Use \:ref:`foo` literally, then see :ref:`foo`.",
                unit,
            ),
            [(36, 46, ":ref:`foo`")],
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
