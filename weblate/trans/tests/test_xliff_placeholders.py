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

from translate.storage.placeables.strelem import StringElem
from translate.storage.xliff import xlifffile

from weblate.trans.util import xliff_string_to_rich, rich_to_xliff_string


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

    def test_xliff_roundtrip(self):
        source = b'''<?xml version='1.0' encoding='UTF-8'?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.2" xsi:schemaLocation="urn:oasis:names:tc:xliff:document:1.2 xliff-core-1.2-transitional.xsd">
  <file datatype="xml" source-language="en-US" target-language="en-US" original="Translation Test">
    <body>
      <group id="body">
        <trans-unit id="1761676329" size-unit="char" translate="yes" xml:space="preserve">
          <source>T: <x id="INTERPOLATION" equiv-text="{{ angularExpression }}"/></source>
        </trans-unit>
      </group>
    </body>
  </file>
</xliff>
'''
        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual(
            'T: <x id="INTERPOLATION" equiv-text="{{ angularExpression }}"/>',
            string
        )
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertEqual(source, bytes(store))

    def test_xliff_roundtrip_unknown(self):
        source = b'''<?xml version='1.0' encoding='UTF-8'?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.2" xsi:schemaLocation="urn:oasis:names:tc:xliff:document:1.2 xliff-core-1.2-transitional.xsd">
  <file datatype="xml" source-language="en-US" target-language="en-US" original="Translation Test">
    <body>
      <group id="body">
        <trans-unit id="1761676329" size-unit="char" translate="yes" xml:space="preserve">
          <source>T: <mrk mtype="protected">%s</mrk></source>
        </trans-unit>
      </group>
    </body>
  </file>
</xliff>
'''
        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual(
            'T: <mrk mtype="protected">%s</mrk>',
            string
        )
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertEqual(source, bytes(store))
