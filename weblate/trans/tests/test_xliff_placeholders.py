# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

"""
Tests for XLIFF rich string.
"""

from django.test import TestCase

from weblate.trans.util import xliff_string_to_rich, rich_to_xliff_string
from translate.storage.placeables.strelem import StringElem


class XliffPlaceholdersTest(TestCase):

    def test_bidirectional_xliff_string(self):
        cases = [
            'foo <x id="INTERPOLATION" equiv-text="{{ angularExpression }}"/> bar',
            '',
            'hello world',
            'hello <p>world</p>'
        ]

        for string in cases:
            rich = xliff_string_to_rich(string)
            self.assertTrue(isinstance(rich, list))
            self.assertTrue(isinstance(rich[0], StringElem))

            final_string = rich_to_xliff_string(rich)
            self.assertEqual(string, final_string)
