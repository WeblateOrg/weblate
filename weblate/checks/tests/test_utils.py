#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
        self.assertEqual(
            highlight_string(
                "simple {format} string", MockUnit(flags="python-brace-format")
            ),
            [(7, 15, "{format}")],
        )

    def test_multi(self):
        self.assertEqual(
            highlight_string(
                "simple {format} %d string",
                MockUnit(flags="python-brace-format, python-format"),
            ),
            [(7, 15, "{format}"), (16, 18, "%d")],
        )

    def test_overlap(self):
        self.assertEqual(
            highlight_string(
                'nested <a href="{format}">string</a>',
                MockUnit(flags="python-brace-format"),
            ),
            [(7, 26, '<a href="{format}">'), (32, 36, "</a>")],
        )
