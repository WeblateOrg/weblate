# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from StringIO import StringIO
from unittest import TestCase
from weblate.trans.formats import (
    AutoFormat, PoFormat, AndroidFormat, PropertiesFormat,
    JSONFormat, RESXFormat, PhpFormat, XliffFormat,
    FILE_FORMATS,
)
from weblate.trans.tests.utils import get_test_file
from translate.storage.po import pofile

TEST_PO = get_test_file('cs.po')
TEST_JSON = get_test_file('cs.json')
TEST_PHP = get_test_file('cs.php')
TEST_PROPERTIES = get_test_file('swing.properties')
TEST_ANDROID = get_test_file('strings.xml')
TEST_XLIFF = get_test_file('cs.xliff')
TEST_POT = get_test_file('hello.pot')
TEST_POT_UNICODE = get_test_file('unicode.pot')
TEST_RESX = get_test_file('cs.resx')


class AutoLoadTest(TestCase):
    def single_test(self, filename, fileclass):
        with open(filename, 'r') as handle:
            store = AutoFormat.parse(handle)
            self.assertIsInstance(store, fileclass)

    def test_po(self):
        self.single_test(TEST_PO, PoFormat)
        self.single_test(TEST_POT, PoFormat)

    def test_json(self):
        self.single_test(TEST_JSON, JSONFormat)

    def test_php(self):
        self.single_test(TEST_PHP, PhpFormat)

    def test_properties(self):
        self.single_test(TEST_PROPERTIES, PropertiesFormat)

    def test_android(self):
        self.single_test(TEST_ANDROID, AndroidFormat)

    def test_xliff(self):
        self.single_test(TEST_XLIFF, XliffFormat)

    def test_resx(self):
        if 'resx' in FILE_FORMATS:
            self.single_test(TEST_RESX, RESXFormat)

    def test_content(self):
        """Test content based guess from ttkit"""
        with open(TEST_PO, 'r') as handle:
            data = handle.read()

        handle = StringIO(data)
        store = AutoFormat.parse(handle)
        self.assertIsInstance(store, AutoFormat)
        self.assertIsInstance(store.store, pofile)


class AutoFormatTest(TestCase):
    FORMAT = AutoFormat
    FILE = TEST_PO
    BASE = TEST_POT
    MIME = 'text/x-gettext-catalog'
    EXT = 'po'
    COUNT = 5
    MATCH = 'msgid_plural'
    MASK = 'po/*.po'
    EXPECTED_PATH = 'po/cs_CZ.po'
    FIND = u'Hello, world!\n'
    FIND_MATCH = u'Ahoj světe!\n'

    def test_parse(self):
        storage = self.FORMAT(self.FILE)
        self.assertEqual(storage.count_units(), self.COUNT)
        self.assertEqual(storage.mimetype, self.MIME)
        self.assertEqual(storage.extension, self.EXT)

    def test_find(self):
        storage = self.FORMAT(self.FILE)
        unit, add = storage.find_unit('', self.FIND)
        self.assertFalse(add)
        if self.COUNT == 0:
            self.assertTrue(unit is None)
        else:
            self.assertEqual(unit.get_target(), self.FIND_MATCH)

    def test_add(self):
        if self.FORMAT.supports_new_language():
            self.assertTrue(self.FORMAT.is_valid_base_for_new(self.BASE))
            out = tempfile.NamedTemporaryFile()
            self.FORMAT.add_language(out.name, 'cs', self.BASE)
            data = out.read()
            self.assertTrue(self.MATCH in data)
            out.close()

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, 'cs_CZ'
            ),
            self.EXPECTED_PATH
        )


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat

    def test_add_encoding(self):
        out = tempfile.NamedTemporaryFile()
        self.FORMAT.add_language(out.name, 'cs', TEST_POT_UNICODE)
        data = out.read().decode('utf-8')
        self.assertTrue(u'Michal Čihař' in data)
        out.close()


class PropertiesFormatTest(AutoFormatTest):
    FORMAT = PropertiesFormat
    FILE = TEST_PROPERTIES
    MIME = 'text/plain'
    COUNT = 12
    EXT = 'properties'
    MASK = 'java/swing_messages_*.properties'
    EXPECTED_PATH = 'java/swing_messages_cs_CZ.properties'
    FIND = 'IGNORE'
    FIND_MATCH = 'Ignore'
    MATCH = '\n'


class JSONFormatTest(AutoFormatTest):
    FORMAT = JSONFormat
    FILE = TEST_JSON
    MIME = 'application/json'
    COUNT = 4
    EXT = 'json'
    MASK = 'json/*.json'
    EXPECTED_PATH = 'json/cs_CZ.json'
    MATCH = '{}\n'
    BASE = ''


class PhpFormatTest(AutoFormatTest):
    FORMAT = PhpFormat
    FILE = TEST_PHP
    MIME = 'text/x-php'
    COUNT = 4
    EXT = 'php'
    MASK = 'php/*/admin.php'
    EXPECTED_PATH = 'php/cs_CZ/admin.php'
    MATCH = '<?php\n'
    FIND = '$LANG[\'foo\']'
    FIND_MATCH = 'bar'


class AndroidFormatTest(AutoFormatTest):
    FORMAT = AndroidFormat
    FILE = TEST_ANDROID
    MIME = 'application/xml'
    EXT = 'xml'
    COUNT = 0
    MATCH = '<resources></resources>'
    MASK = 'res/values-*/strings.xml'
    EXPECTED_PATH = 'res/values-cs-rCZ/strings.xml'


class XliffFormatTest(AutoFormatTest):
    FORMAT = XliffFormat
    FILE = TEST_XLIFF
    BASE = TEST_XLIFF
    MIME = 'application/x-xliff'
    EXT = 'xlf'
    COUNT = 4
    MATCH = '<file target-language="cs">'
    FIND_MATCH = u''
    MASK = 'loc/*/default.xliff'
    EXPECTED_PATH = 'loc/cs_CZ/default.xliff'


if 'resx' in FILE_FORMATS:
    class RESXFormatTest(AutoFormatTest):
        FORMAT = RESXFormat
        FILE = TEST_RESX
        MIME = 'text/microsoft-resx'
        EXT = 'resx'
        COUNT = 4
        MASK = 'resx/*.resx'
        EXPECTED_PATH = 'resx/cs_CZ.resx'
        FIND = u'Hello'
        FIND_MATCH = u''
        MATCH = '<root></root>'
