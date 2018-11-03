# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
"""File format specific behavior."""
from __future__ import unicode_literals

from io import BytesIO
import os.path
from unittest import TestCase, SkipTest

from django.test import SimpleTestCase
from django.utils.encoding import force_text

import translate.__version__
from translate.storage.po import pofile

from weblate.lang.models import Language
from weblate.formats.auto import AutoFormat
from weblate.formats.ttkit import (
    PoFormat, AndroidFormat, PropertiesFormat, JoomlaFormat, JSONFormat,
    JSONNestedFormat, RESXFormat, PhpFormat, XliffFormat, TSFormat, YAMLFormat,
    RubyYAMLFormat, DTDFormat, WindowsRCFormat, WebExtensionJSONFormat,
    PoXliffFormat, CSVFormat,
)
from weblate.formats.models import FILE_FORMATS
from weblate.formats.auto import detect_filename
from weblate.trans.tests.utils import get_test_file, TempDirMixin


TEST_PO = get_test_file('cs.po')
TEST_CSV = get_test_file('cs-mono.csv')
TEST_JSON = get_test_file('cs.json')
TEST_NESTED_JSON = get_test_file('cs-nested.json')
TEST_WEBEXT_JSON = get_test_file('cs-webext.json')
TEST_PHP = get_test_file('cs.php')
TEST_JOOMLA = get_test_file('cs.ini')
TEST_PROPERTIES = get_test_file('swing.properties')
TEST_ANDROID = get_test_file('strings.xml')
TEST_XLIFF = get_test_file('cs.xliff')
TEST_POT = get_test_file('hello.pot')
TEST_POT_UNICODE = get_test_file('unicode.pot')
TEST_RESX = get_test_file('cs.resx')
TEST_TS = get_test_file('cs.ts')
TEST_YAML = get_test_file('cs.pyml')
TEST_RUBY_YAML = get_test_file('cs.ryml')
TEST_DTD = get_test_file('cs.dtd')
TEST_RC = get_test_file('cs-CZ.rc')
TEST_HE_CLDR = get_test_file('he-cldr.po')
TEST_HE_CUSTOM = get_test_file('he-custom.po')
TEST_HE_SIMPLE = get_test_file('he-simple.po')
TEST_HE_THREE = get_test_file('he-three.po')


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
        if 'php' not in FILE_FORMATS:
            raise SkipTest('PHP not supported')
        self.single_test(TEST_PHP, PhpFormat)

    def test_properties(self):
        self.single_test(TEST_PROPERTIES, PropertiesFormat)

    def test_joomla(self):
        if 'joomla' not in FILE_FORMATS:
            raise SkipTest('Joomla not supported')
        self.single_test(TEST_JOOMLA, JoomlaFormat)

    def test_android(self):
        self.single_test(TEST_ANDROID, AndroidFormat)

    def test_xliff(self):
        self.single_test(TEST_XLIFF, XliffFormat)

    def test_resx(self):
        if 'resx' not in FILE_FORMATS:
            raise SkipTest('RESX not supported')
        self.single_test(TEST_RESX, RESXFormat)

    def test_yaml(self):
        if 'yaml' not in FILE_FORMATS:
            raise SkipTest('YAML not supported')
        self.single_test(TEST_YAML, YAMLFormat)

    def test_ruby_yaml(self):
        if 'ruby-yaml' not in FILE_FORMATS:
            raise SkipTest('YAML not supported')
        self.single_test(TEST_RUBY_YAML, RubyYAMLFormat)

    def test_content(self):
        """Test content based guess from ttkit"""
        with open(TEST_PO, 'rb') as handle:
            data = handle.read()

        handle = BytesIO(data)
        store = AutoFormat.parse(handle)
        self.assertIsInstance(store, AutoFormat)
        self.assertIsInstance(store.store, pofile)


class AutoFormatTest(SimpleTestCase, TempDirMixin):
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
    FIND_CONTEXT = ''
    FIND_MATCH = 'Ahoj světe!\n'
    NEW_UNIT_MATCH = b'\nmsgid "key"\nmsgstr "Source string"\n'
    allow_database_queries = True

    def setUp(self):
        super(AutoFormatTest, self).setUp()
        self.create_temp()
        if self.FORMAT.format_id not in FILE_FORMATS:
            raise SkipTest(
                'File format {0} is not supported!'.format(
                    self.FORMAT.format_id
                )
            )

    def tearDown(self):
        super(AutoFormatTest, self).tearDown()
        self.remove_temp()

    def test_parse(self):
        storage = self.FORMAT(self.FILE)
        self.assertEqual(storage.count_units(), self.COUNT)
        self.assertEqual(storage.mimetype, self.MIME)
        self.assertEqual(storage.extension, self.EXT)

    def test_save(self, edit=False):
        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, 'test.{0}'.format(self.EXT))

        # Write test data to file
        with open(testfile, 'wb') as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.FORMAT(testfile)

        if edit:
            units = list(storage.all_units())
            units[0].set_target('Nazdar, svete!\n')

        # Save test file
        storage.save()

        # Read new content
        with open(testfile, 'rb') as handle:
            newdata = handle.read()

        # Check if content matches
        if edit:
            with self.assertRaises(AssertionError):
                self.assert_same(force_text(newdata), force_text(testdata))
        else:
            self.assert_same(force_text(newdata), force_text(testdata))

    def test_edit(self):
        self.test_save(True)

    def assert_same(self, newdata, testdata):
        """Content aware comparison.

        This can be implemented in subclasses to implement content
        aware comparing of translation files.
        """
        self.assertEqual(testdata.strip(), newdata.strip())

    def test_find(self):
        storage = self.FORMAT(self.FILE)
        unit, add = storage.find_unit(self.FIND_CONTEXT, self.FIND)
        self.assertFalse(add)
        if self.COUNT == 0:
            self.assertTrue(unit is None)
        else:
            self.assertIsNotNone(unit)
            self.assertEqual(unit.get_target(), self.FIND_MATCH)

    def test_add(self):
        self.assertTrue(self.FORMAT.is_valid_base_for_new(self.BASE, True))
        out = os.path.join(self.tempdir, 'test.{0}'.format(self.EXT))
        self.FORMAT.add_language(
            out,
            Language.objects.get(code='cs'),
            self.BASE
        )
        with open(out, 'r') as handle:
            data = handle.read()
        self.assertTrue(self.MATCH in data)

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, 'cs_CZ'
            ),
            self.EXPECTED_PATH
        )

    def test_new_unit(self):
        if not self.FORMAT.can_add_unit:
            raise SkipTest('Not supported')
        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, 'test.{0}'.format(self.EXT))

        # Write test data to file
        with open(testfile, 'wb') as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.FORMAT(testfile)

        # Add new unit
        storage.new_unit('key', 'Source string')

        # Read new content
        with open(testfile, 'rb') as handle:
            newdata = handle.read()

        # Check if content matches
        if isinstance(self.NEW_UNIT_MATCH, tuple):
            for match in self.NEW_UNIT_MATCH:
                self.assertIn(match, newdata)
        else:
            self.assertIn(self.NEW_UNIT_MATCH, newdata)


class XMLMixin(object):
    def assert_same(self, newdata, testdata):
        self.assertXMLEqual(newdata, testdata)


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat

    def test_add_encoding(self):
        out = os.path.join(self.tempdir, 'test.po')
        self.FORMAT.add_language(
            out,
            Language.objects.get(code='cs'),
            TEST_POT_UNICODE
        )
        with open(out, 'rb') as handle:
            data = handle.read().decode('utf-8')
        self.assertTrue('Michal Čihař' in data)

    def load_plural(self, filename):
        with open(filename, 'rb') as handle:
            store = self.FORMAT(handle)
            return store.get_plural(Language.objects.get(code='he'))

    def test_plurals(self):
        self.assertEqual(
            self.load_plural(TEST_HE_CLDR).equation,
            '(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))'
        )
        self.assertEqual(
            self.load_plural(TEST_HE_CUSTOM).equation,
            '(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 10) ? 2 : 3))'
        )
        self.assertEqual(
            self.load_plural(TEST_HE_SIMPLE).equation,
            '(n != 1)'
        )
        self.assertEqual(
            self.load_plural(TEST_HE_THREE).equation,
            'n==1 ? 0 : n==2 ? 2 : 1'
        )


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
    NEW_UNIT_MATCH = b'\nkey=Source string\n'

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            newdata.strip().splitlines(),
            testdata.strip().splitlines(),
        )


class JoomlaFormatTest(AutoFormatTest):
    FORMAT = JoomlaFormat
    FILE = TEST_JOOMLA
    MIME = 'text/plain'
    COUNT = 4
    EXT = 'ini'
    MASK = 'joomla/*.ini'
    EXPECTED_PATH = 'joomla/cs_CZ.ini'
    MATCH = '\n'
    FIND = 'HELLO'
    FIND_MATCH = 'Ahoj "světe"!\n'
    NEW_UNIT_MATCH = b'\nkey=Source string\n'


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
    NEW_UNIT_MATCH = b'\n    "key": "Source string"\n'

    def assert_same(self, newdata, testdata):
        self.assertJSONEqual(newdata, testdata)


class JSONNestedFormatTest(JSONFormatTest):
    FORMAT = JSONNestedFormat
    FILE = TEST_NESTED_JSON
    COUNT = 4
    MASK = 'json-nested/*.json'
    EXPECTED_PATH = 'json-nested/cs_CZ.json'
    FIND = 'weblate.hello'


class WebExtesionJSONFormatTest(JSONFormatTest):
    FORMAT = WebExtensionJSONFormat
    FILE = TEST_WEBEXT_JSON
    COUNT = 4
    MASK = 'webextension/_locales/*/messages.json'
    EXPECTED_PATH = 'webextension/_locales/cs_CZ/messages.json'
    FIND = 'hello'
    NEW_UNIT_MATCH = (
        b'\n    "key": {\n        "message": "Source string"\n    }\n'
    )

    def test_new_unit(self):
        if translate.__version__.ver <= (2, 2, 5):
            raise SkipTest('Broken WebExtension support in translate-toolkit')
        super(WebExtesionJSONFormatTest, self).test_new_unit()


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
    BASE = ''
    NEW_UNIT_MATCH = b'\nkey = \'Source string\';\n'


class AndroidFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = AndroidFormat
    FILE = TEST_ANDROID
    MIME = 'application/xml'
    EXT = 'xml'
    COUNT = 1
    MATCH = '<resources></resources>'
    MASK = 'res/values-*/strings.xml'
    EXPECTED_PATH = 'res/values-cs-rCZ/strings.xml'
    FIND = 'Hello, world!\n'
    FIND_CONTEXT = 'hello'
    FIND_MATCH = 'Hello, world!\n'
    BASE = ''
    NEW_UNIT_MATCH = b'\n<string name="key">Source string</string>\n'


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
    NEW_UNIT_MATCH = (
        b'<trans-unit xml:space="preserve" id="key" approved="no">'
        b'<source>key</source>'
        b'<target state="translated">Source string</target></trans-unit>'
    )


class PoXliffFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = PoXliffFormat
    FILE = TEST_XLIFF
    BASE = TEST_XLIFF
    MIME = 'application/x-xliff'
    EXT = 'xlf'
    COUNT = 4
    MATCH = '<file target-language="cs">'
    FIND_MATCH = ''
    MASK = 'loc/*/default.xliff'
    EXPECTED_PATH = 'loc/cs_CZ/default.xliff'
    NEW_UNIT_MATCH = (
        b'<trans-unit xml:space="preserve" id="key" approved="no">'
        b'<source>key</source>'
        b'<target state="translated">Source string</target></trans-unit>'
    )


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
    MATCH = 'text/microsoft-resx'
    BASE = ''
    NEW_UNIT_MATCH = (
        b'<data name="key" xml:space="preserve">',
        b'<value>Source string</value>',
    )


class YAMLFormatTest(AutoFormatTest):
    FORMAT = YAMLFormat
    FILE = TEST_YAML
    BASE = TEST_YAML
    MIME = 'text/yaml'
    EXT = 'yml'
    COUNT = 4
    MASK = 'yaml/*.yml'
    EXPECTED_PATH = 'yaml/cs_CZ.yml'
    FIND = 'weblate->hello'
    FIND_MATCH = ''
    MATCH = 'weblate:'
    NEW_UNIT_MATCH = b'\nkey: Source string\n'

    def assert_same(self, newdata, testdata, equal=True):
        # Fixup quotes as different translate toolkit versions behave
        # differently
        self.assertEqual(
            newdata.replace("'", '"').strip().splitlines(),
            testdata.strip().splitlines(),
        )


class RubyYAMLFormatTest(YAMLFormatTest):
    FORMAT = RubyYAMLFormat
    FILE = TEST_RUBY_YAML
    BASE = TEST_RUBY_YAML
    NEW_UNIT_MATCH = b'\n  key: Source string\n'


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
    FIND_MATCH = 'Ahoj svete!\n'
    NEW_UNIT_MATCH = (
        b'\n<message><source>key</source>'
        b'<translation>Source string</translation>\n    </message>'
    )

    def assert_same(self, newdata, testdata):
        # Comparing of XML with doctype fails...
        newdata = newdata.replace('<!DOCTYPE TS>', '')
        testdata = testdata.replace('<!DOCTYPE TS>', '')
        super(TSFormatTest, self).assert_same(newdata, testdata)


class DTDFormatTest(AutoFormatTest):
    FORMAT = DTDFormat
    FILE = TEST_DTD
    BASE = TEST_DTD
    MIME = 'application/xml-dtd'
    EXT = 'dtd'
    COUNT = 4
    MASK = 'dtd/*.dtd'
    EXPECTED_PATH = 'dtd/cs_CZ.dtd'
    MATCH = '<!ENTITY'
    FIND = 'hello'
    FIND_MATCH = ''
    NEW_UNIT_MATCH = b'\n<!ENTITY key "Source string">\n'


class WindowsRCFormatTest(AutoFormatTest):
    FORMAT = WindowsRCFormat
    FILE = TEST_RC
    BASE = TEST_RC
    MIME = 'text/plain'
    EXT = 'rc'
    COUNT = 4
    MASK = 'rc/*.rc'
    EXPECTED_PATH = 'rc/cs-CZ.rc'
    MATCH = 'STRINGTABLE'
    FIND = 'Hello, world!\n'
    FIND_MATCH = 'Hello, world!\n'
    NEW_UNIT_MATCH = None

    def test_edit(self):
        raise SkipTest('Known to be broken')


class CSVFormatTest(AutoFormatTest):
    FORMAT = CSVFormat
    FILE = TEST_CSV
    MIME = 'text/csv'
    COUNT = 4
    EXT = 'csv'
    MASK = 'csv/*.csv'
    EXPECTED_PATH = 'csv/cs_CZ.csv'
    MATCH = 'HELLO'
    BASE = TEST_CSV
    FIND = 'HELLO'
    FIND_MATCH = 'Hello, world!\r\n'
    NEW_UNIT_MATCH = b'"key","Source string"\r\n'
