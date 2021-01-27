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

"""Tests for XLIFF rich string."""

from django.test import TestCase
from translate.storage.placeables.strelem import StringElem
from translate.storage.xliff import xlifffile

from weblate.trans.tests.utils import get_test_file
from weblate.trans.util import rich_to_xliff_string, xliff_string_to_rich

TEST_X = get_test_file("placeholder-x.xliff")
TEST_MRK = get_test_file("placeholder-mrk.xliff")


class XliffPlaceholdersTest(TestCase):
    def test_bidirectional_xliff_string(self):
        cases = [
            'foo <x id="INTERPOLATION" equiv-text="{{ angular }}"/> bar',
            "",
            "hello world",
            "hello <p>world</p>",
        ]

        for string in cases:
            rich = xliff_string_to_rich(string)
            self.assertTrue(isinstance(rich, list))
            self.assertTrue(isinstance(rich[0], StringElem))

            final_string = rich_to_xliff_string(rich)
            self.assertEqual(string, final_string)

    def test_xliff_roundtrip(self):
        with open(TEST_X, "rb") as handle:
            source = handle.read()

        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual(
            'T: <x id="INTERPOLATION" equiv-text="{{ angular }}"/>', string
        )
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertEqual(source, bytes(store))

    def test_xliff_roundtrip_unknown(self):
        with open(TEST_MRK, "rb") as handle:
            source = handle.read()

        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual('T: <mrk mtype="protected">%s</mrk>', string)
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertEqual(source, bytes(store))
