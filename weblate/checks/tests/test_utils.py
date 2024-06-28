# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.checks.utils import highlight_string


class HightlightTestCase(SimpleTestCase):
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
            highlight_string(unit.source, unit, hightlight_syntax=True),
            [(12, 13, "`"), (18, 46, "<https://www.sphinx-doc.org>"), (46, 48, "`_")],
        )
        self.assertEqual(
            highlight_string(
                "Hello `world <https://weblate.org>`_", unit, hightlight_syntax=True
            ),
            [(6, 7, "`"), (13, 34, "<https://weblate.org>"), (34, 36, "`_")],
        )
        self.assertEqual(
            highlight_string("Hello **world**", unit, hightlight_syntax=True),
            [(6, 8, "**"), (13, 15, "**")],
        )
        self.assertEqual(
            highlight_string("Hello *world*", unit, hightlight_syntax=True),
            [(6, 7, "*"), (12, 13, "*")],
        )
