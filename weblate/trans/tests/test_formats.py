# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
'''
File format specific behavior.
'''
from __future__ import unicode_literals

from io import BytesIO
import tempfile
from unittest import TestCase, SkipTest

from django.test import SimpleTestCase
from django.utils.encoding import force_text

import six

from translate.storage.po import pofile

from weblate.lang.models import Language
from weblate.trans.formats import (
    AutoFormat, PoFormat, AndroidFormat, PropertiesFormat,
    JSONFormat, RESXFormat, PhpFormat, XliffFormat, TSFormat,
    FILE_FORMATS, detect_filename,
)
from weblate.trans.tests.utils import get_test_file


TEST_PO = get_test_file('cs.po')
TEST_JSON = get_test_file('cs.json')
TEST_PHP = get_test_file('cs.php')
TEST_PROPERTIES = get_test_file('swing.properties')
TEST_ANDROID = get_test_file('strings.xml')
TEST_XLIFF = get_test_file('cs.xliff')
TEST_POT = get_test_file('hello.pot')
TEST_POT_UNICODE = get_test_file('unicode.pot')
TEST_RESX = get_test_file('cs.resx')
TEST_TS = get_test_file('cs.ts')


class AutoLoadTest(TestCase):
    def single_test(self, filename, fileclass):
        with open(filename, 'rb') as handle:
            store = AutoFormat.parse(handle)
            self.assertIsInstance(store, fileclass)
        self.assertEqual(fileclass, detect_filename(filename))

    def test_detect_android(self):
        self.assertEqual(
            AndroidFormat,
            detect_filename('foo/bar/strings_baz.xml')
        )

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
        with open(TEST_PO, 'rb') as handle:
            data = handle.read()

        handle = BytesIO(data)
        store = AutoFormat.parse(handle)
        self.assertIsInstance(store, AutoFormat)
        self.assertIsInstance(store.store, pofile)


class AutoFormatTest(SimpleTestCase):
    FORMAT = AutoFormat
    FILE = TEST_PO
    BASE = TEST_POT
    MIME = 'text/x-gettext-catalog'
    EXT = 'po'
    COUNT = 5
    MATCH = 'msgid_plural'
    MASK = 'po/*.po'
    EXPECTED_PATH = 'po/cs_CZ.po'
    FIND = 'Hello, world!\n'
    FIND_MATCH = 'Ahoj světe!\n'

    def test_parse(self):
        storage = self.FORMAT(self.FILE)
        self.assertEqual(storage.count_units(), self.COUNT)
        self.assertEqual(storage.mimetype, self.MIME)
        self.assertEqual(storage.extension, self.EXT)

    def test_save(self):
        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = tempfile.NamedTemporaryFile(
            suffix='.{0}'.format(self.EXT),
            mode='wb+'
        )
        try:
            # Write test data to file
            testfile.write(testdata)
            testfile.flush()

            # Parse test file
            storage = self.FORMAT(testfile.name)

            # Save test file
            storage.save()

            # Read new content
            with open(testfile.name, 'rb') as handle:
                newdata = handle.read()

            # Check if content matches
            self.assert_same(
                force_text(newdata),
                force_text(testdata)
            )
        finally:
            testfile.close()

    def assert_same(self, newdata, testdata):
        """Content aware comparison.

        This can be implemented in subclasses to implement content
        aware comparing of translation files.
        """
        # Show full diff on error
        # pylint: disable=C0103
        self.maxDiff = None
        self.assertEqual(testdata.strip(), newdata.strip())

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
            out = tempfile.NamedTemporaryFile(
                suffix='.{0}'.format(self.EXT),
                mode='w+'
            )
            self.FORMAT.add_language(out.name, Language(code='cs'), self.BASE)
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


class XMLMixin(object):
    def assert_same(self, newdata, testdata):
        self.assertXMLEqual(newdata, testdata)


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat

    def test_add_encoding(self):
        out = tempfile.NamedTemporaryFile()
        self.FORMAT.add_language(
            out.name, Language(code='cs'), TEST_POT_UNICODE
        )
        data = out.read().decode('utf-8')
        self.assertTrue('Michal Čihař' in data)
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

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            newdata.strip().splitlines(),
            testdata.strip().splitlines(),
        )


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

    def assert_same(self, newdata, testdata):
        self.assertJSONEqual(newdata, testdata)


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


class AndroidFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = AndroidFormat
    FILE = TEST_ANDROID
    MIME = 'application/xml'
    EXT = 'xml'
    COUNT = 0
    MATCH = '<resources></resources>'
    MASK = 'res/values-*/strings.xml'
    EXPECTED_PATH = 'res/values-cs-rCZ/strings.xml'


class XliffFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = XliffFormat
    FILE = TEST_XLIFF
    BASE = TEST_XLIFF
    MIME = 'application/x-xliff'
    EXT = 'xlf'
    COUNT = 4
    MATCH = '<file target-language="cs">'
    FIND_MATCH = ''
    MASK = 'loc/*/default.xliff'
    EXPECTED_PATH = 'loc/cs_CZ/default.xliff'


class RESXFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = RESXFormat
    FILE = TEST_RESX
    MIME = 'text/microsoft-resx'
    EXT = 'resx'
    COUNT = 4
    MASK = 'resx/*.resx'
    EXPECTED_PATH = 'resx/cs_CZ.resx'
    FIND = 'Hello'
    FIND_MATCH = ''
    MATCH = '<root></root>'

    def setUp(self):
        super(RESXFormatTest, self).setUp()
        if 'resx' not in FILE_FORMATS:
            raise SkipTest('resx not supported!')


class TSFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = TSFormat
    FILE = TEST_TS
    BASE = TEST_TS
    MIME = 'application/x-linguist'
    EXT = 'ts'
    COUNT = 5
    MASK = 'ts/*.ts'
    EXPECTED_PATH = 'ts/cs_CZ.ts'
    MATCH = '<TS version="2.0" language="cs">'

    def assert_same(self, newdata, testdata):
        # Comparing of XML with doctype fails...
        newdata = newdata.replace('<!DOCTYPE TS>', '')
        testdata = testdata.replace('<!DOCTYPE TS>', '')
        # Magic for Python 2.x
        if six.PY2:
            testdata = testdata.encode('utf-8')
            newdata = newdata.encode('utf-8')
        super(TSFormatTest, self).assert_same(newdata, testdata)
