# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
'''
File format specific behavior.
'''
import tempfile
from unittest import TestCase
from trans.formats import (
    AutoFormat, PoFormat, AndroidFormat,
)
from trans.tests.util import get_test_file
from django.utils.unittest import skipUnless

TEST_PO = get_test_file('cs.po')
TEST_ANDROID = get_test_file('strings.xml')
TEST_POT = get_test_file('hello.pot')


class AutoFormatTest(TestCase):
    FORMAT = AutoFormat
    FILE = TEST_PO
    BASE = TEST_POT
    MIME = 'text/x-gettext-catalog'
    EXT = 'po'
    COUNT = 5

    def test_parse(self):
        storage = self.FORMAT(self.FILE)
        self.assertEquals(storage.count_units(), self.COUNT)
        self.assertEquals(storage.mimetype, self.MIME)
        self.assertEquals(storage.extension, self.EXT)

    def test_find(self):
        storage = self.FORMAT(self.FILE)
        unit, add = storage.find_unit('', 'Hello, world!\n')
        self.assertFalse(add)
        if self.COUNT == 0:
            self.assertIsNone(unit)
        else:
            self.assertEquals(unit.get_target(), 'Ahoj světe!\n')

    def test_add(self):
        if self.FORMAT.supports_new_language(self.BASE):
            out = tempfile.NamedTemporaryFile()
            self.FORMAT.add_language(out.name, 'cs', self.BASE)


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat


class AndroidFormatTest(AutoFormatTest):
    FORMAT = AndroidFormat
    FILE = TEST_ANDROID
    MIME = 'application/xml'
    EXT = 'xml'
    COUNT = 0
