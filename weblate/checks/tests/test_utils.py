#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.test import SimpleTestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.checks.utils import highlight_string


class HightlightTestCase(SimpleTestCase):
    def test_simple(self):
        unit = MockUnit(
            source="simple {format} string",
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}")],
        )

    def test_multi(self):
        unit = MockUnit(
            source="simple {format} %d string",
            flags="python-brace-format, python-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}"), (16, 18, "%d")],
        )

    def test_overlap(self):
        unit = MockUnit(
            source='nested <a href="{format}">string</a>',
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 26, '<a href="{format}">'), (32, 36, "</a>")],
        )

    def test_syntax(self):
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
