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
    AutoFormat, PoFormat,
)
from trans.tests.util import get_test_file
from django.utils.unittest import skipUnless

TEST_PO = get_test_file('cs.po')
TEST_POT = get_test_file('hello.pot')


class AutoFormatTest(TestCase):
    FORMAT = AutoFormat

    def test_parse(self):
        storage = self.FORMAT(TEST_PO)
        self.assertEquals(storage.count_units(), 5)
        self.assertEquals(storage.mimetype, 'text/x-gettext-catalog')
        self.assertEquals(storage.extension, 'po')

    def test_find(self):
        storage = self.FORMAT(TEST_PO)
        unit, add = storage.find_unit('', 'Hello, world!\n')
        self.assertFalse(add)
        self.assertEquals(unit.get_target(), 'Ahoj světe!\n')

    def test_add(self):
        if self.FORMAT.supports_new_language(TEST_POT):
            out = tempfile.NamedTemporaryFile()
            self.FORMAT.add_language(out.name, 'cs', TEST_POT)


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat
