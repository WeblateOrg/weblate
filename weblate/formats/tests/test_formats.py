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
"""File format specific behavior."""

import os.path
import shutil
from io import BytesIO
from unittest import SkipTest, TestCase

from lxml import etree
from translate.storage.po import pofile

from weblate.formats.auto import AutodetectFormat, detect_filename
from weblate.formats.base import UpdateError
from weblate.formats.models import FILE_FORMATS
from weblate.formats.ttkit import (
    AndroidFormat,
    CSVFormat,
    CSVSimpleFormat,
    DTDFormat,
    FlatXMLFormat,
    GWTFormat,
    INIFormat,
    InnoSetupINIFormat,
    JoomlaFormat,
    JSONFormat,
    JSONNestedFormat,
    LaravelPhpFormat,
    PhpFormat,
    PoFormat,
    PoXliffFormat,
    PropertiesFormat,
    RESXFormat,
    RubyYAMLFormat,
    TBXFormat,
    TSFormat,
    WebExtensionJSONFormat,
    XliffFormat,
    XWikiFullPageFormat,
    XWikiPagePropertiesFormat,
    XWikiPropertiesFormat,
    YAMLFormat,
)
from weblate.lang.models import Language
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import TempDirMixin, get_test_file
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED

TEST_PO = get_test_file("cs.po")
TEST_CSV = get_test_file("cs-mono.csv")
TEST_CSV_NOHEAD = get_test_file("cs.csv")
TEST_FLATXML = get_test_file("cs-flat.xml")
TEST_JSON = get_test_file("cs.json")
TEST_NESTED_JSON = get_test_file("cs-nested.json")
TEST_WEBEXT_JSON = get_test_file("cs-webext.json")
TEST_PHP = get_test_file("cs.php")
TEST_LARAVEL = get_test_file("laravel.php")
TEST_JOOMLA = get_test_file("cs.joomla.ini")
TEST_INI = get_test_file("cs.ini")
TEST_PROPERTIES = get_test_file("swing.properties")
TEST_GWT = get_test_file("gwt.properties")
TEST_ANDROID = get_test_file("strings.xml")
TEST_XLIFF = get_test_file("cs.xliff")
TEST_POXLIFF = get_test_file("cs.poxliff")
TEST_XLIFF_ID = get_test_file("ids.xliff")
TEST_POT = get_test_file("hello.pot")
TEST_POT_UNICODE = get_test_file("unicode.pot")
TEST_RESX = get_test_file("cs.resx")
TEST_TS = get_test_file("cs.ts")
TEST_YAML = get_test_file("cs.pyml")
TEST_RUBY_YAML = get_test_file("cs.ryml")
TEST_DTD = get_test_file("cs.dtd")
TEST_TBX = get_test_file("cs.tbx")
TEST_HE_CLDR = get_test_file("he-cldr.po")
TEST_HE_CUSTOM = get_test_file("he-custom.po")
TEST_HE_SIMPLE = get_test_file("he-simple.po")
TEST_HE_THREE = get_test_file("he-three.po")
TEST_XWIKI_PROPERTIES = get_test_file("xwiki.properties")
TEST_XWIKI_PROPERTIES_NEW_LANGUAGE = get_test_file("xwiki_new_language.properties")
TEST_XWIKI_PAGE_PROPERTIES = get_test_file("XWikiPageProperties.xml")
TEST_XWIKI_PAGE_PROPERTIES_SOURCE = get_test_file("XWikiPagePropertiesSource.xml")
TEST_XWIKI_FULL_PAGE = get_test_file("XWikiFullPage.xml")
TEST_XWIKI_FULL_PAGE_SOURCE = get_test_file("XWikiFullPageSource.xml")


class AutoLoadTest(TestCase):
    def single_test(self, filename, fileclass):
        with open(filename, "rb") as handle:
            store = AutodetectFormat.parse(handle)
            self.assertIsInstance(store, fileclass)
        self.assertEqual(fileclass, detect_filename(filename))

    def test_detect_android(self):
        self.assertEqual(AndroidFormat, detect_filename("foo/bar/strings_baz.xml"))

    def test_po(self):
        self.single_test(TEST_PO, PoFormat)
        self.single_test(TEST_POT, PoFormat)

    def test_json(self):
        self.single_test(TEST_JSON, JSONFormat)

    def test_php(self):
        if "php" not in FILE_FORMATS:
            raise SkipTest("PHP not supported")
        self.single_test(TEST_PHP, PhpFormat)

    def test_properties(self):
        self.single_test(TEST_PROPERTIES, PropertiesFormat)

    def test_joomla(self):
        if "joomla" not in FILE_FORMATS:
            raise SkipTest("Joomla not supported")
        self.single_test(TEST_JOOMLA, JoomlaFormat)

    def test_android(self):
        self.single_test(TEST_ANDROID, AndroidFormat)

    def test_xliff(self):
        self.single_test(TEST_XLIFF, XliffFormat)

    def test_resx(self):
        if "resx" not in FILE_FORMATS:
            raise SkipTest("RESX not supported")
        self.single_test(TEST_RESX, RESXFormat)

    def test_yaml(self):
        if "yaml" not in FILE_FORMATS:
            raise SkipTest("YAML not supported")
        self.single_test(TEST_YAML, YAMLFormat)

    def test_ruby_yaml(self):
        if "ruby-yaml" not in FILE_FORMATS:
            raise SkipTest("YAML not supported")
        self.single_test(TEST_RUBY_YAML, RubyYAMLFormat)

    def test_content(self):
        """Test content based guess from ttkit."""
        with open(TEST_PO, "rb") as handle:
            data = handle.read()

        handle = BytesIO(data)
        store = AutodetectFormat.parse(handle)
        self.assertIsInstance(store, AutodetectFormat)
        self.assertIsInstance(store.store, pofile)


class AutoFormatTest(FixtureTestCase, TempDirMixin):
    FORMAT = AutodetectFormat
    FILE = TEST_PO
    BASE = TEST_POT
    MIME = "text/x-gettext-catalog"
    EXT = "po"
    COUNT = 5
    MATCH = "msgid_plural"
    MASK = "po/*.po"
    EXPECTED_PATH = "po/cs_CZ.po"
    FIND = "Hello, world!\n"
    FIND_CONTEXT = ""
    FIND_MATCH = "Ahoj světe!\n"
    NEW_UNIT_MATCH = b'\nmsgctxt "key"\nmsgid "Source string"\n'
    NEW_UNIT_KEY = "key"
    SUPPORTS_FLAG = True
    EXPECTED_FLAGS = "c-format, max-length:100"
    EDIT_OFFSET = 0
    EDIT_TARGET = "Nazdar, svete!\n"
    MONOLINGUAL = False

    def setUp(self):
        super().setUp()
        self.create_temp()
        if self.FORMAT.format_id not in FILE_FORMATS:
            raise SkipTest(f"File format {self.FORMAT!r} is not supported!")

    def tearDown(self):
        super().tearDown()
        self.remove_temp()

    def parse_file(self, filename):
        if self.MONOLINGUAL:
            return self.FORMAT(filename, template_store=self.FORMAT(filename))
        return self.FORMAT(filename)

    def test_parse(self):
        storage = self.parse_file(self.FILE)
        self.assertEqual(len(storage.all_units), self.COUNT)
        self.assertEqual(storage.mimetype(), self.MIME)
        self.assertEqual(storage.extension(), self.EXT)

    def test_save(self, edit=False):
        # Read test content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Write test data to file
        with open(testfile, "wb") as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile)

        if edit:
            units = storage.all_units
            units[self.EDIT_OFFSET].set_target(self.EDIT_TARGET)

        # Save test file
        storage.save()

        # Read new content
        with open(testfile, "rb") as handle:
            newdata = handle.read()

        # Check if content matches
        if edit:
            with self.assertRaises(AssertionError):
                self.assert_same(newdata, testdata)
        else:
            self.assert_same(newdata, testdata)

    def test_edit(self):
        self.test_save(True)

    def assert_same(self, newdata, testdata):
        """Content aware comparison.

        This can be implemented in subclasses to implement content aware comparing of
        translation files.
        """
        self.assertEqual(testdata.strip(), newdata.strip())

    def test_find(self):
        storage = self.parse_file(self.FILE)
        unit, add = storage.find_unit(self.FIND_CONTEXT, self.FIND)
        self.assertFalse(add)
        if self.COUNT == 0:
            self.assertIn(unit, None)
        else:
            self.assertIsNotNone(unit)
            self.assertEqual(unit.target, self.FIND_MATCH)

    def test_add(self):
        self.assertTrue(self.FORMAT.is_valid_base_for_new(self.BASE, True))
        out = os.path.join(self.tempdir, f"test.{self.EXT}")
        self.FORMAT.add_language(out, Language.objects.get(code="cs"), self.BASE)
        if self.MATCH is None:
            self.assertTrue(os.path.isdir(out))
        else:
            if isinstance(self.MATCH, bytes):
                mode = "rb"
            else:
                mode = "r"
            with open(out, mode) as handle:
                data = handle.read()
            self.assertIn(self.MATCH, data)

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, self.FORMAT.get_language_code("cs_CZ")
            ),
            self.EXPECTED_PATH,
        )

    def test_new_unit(self):
        if not self.FORMAT.can_add_unit:
            raise SkipTest("Not supported")
        # Read test content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, f"test.{self.EXT}")

        # Write test data to file
        with open(testfile, "wb") as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile)

        # Add new unit
        storage.new_unit(self.NEW_UNIT_KEY, "Source string", skip_build=True)
        storage.save()

        # Read new content
        with open(testfile, "rb") as handle:
            newdata = handle.read()

        # Check if content matches
        if isinstance(self.NEW_UNIT_MATCH, tuple):
            for match in self.NEW_UNIT_MATCH:
                self.assertIn(match, newdata)
        else:
            self.assertIn(self.NEW_UNIT_MATCH, newdata)

    def test_flags(self):
        """Check flags on first translatable unit."""
        storage = self.parse_file(self.FILE)
        for unit in storage.content_units:
            self.assertEqual(unit.flags, self.EXPECTED_FLAGS)
            break


class XMLMixin:
    def assert_same(self, newdata, testdata):
        self.assertXMLEqual(newdata.decode(), testdata.decode())


class PoFormatTest(AutoFormatTest):
    FORMAT = PoFormat
    EDIT_OFFSET = 1

    def test_add_encoding(self):
        out = os.path.join(self.tempdir, "test.po")
        self.FORMAT.add_language(out, Language.objects.get(code="cs"), TEST_POT_UNICODE)
        with open(out) as handle:
            data = handle.read()
        self.assertIn("Michal Čihař", data)

    def load_plural(self, filename):
        with open(filename, "rb") as handle:
            store = self.parse_file(handle)
            return store.get_plural(Language.objects.get(code="he"))

    def test_plurals(self):
        self.assertEqual(
            self.load_plural(TEST_HE_CLDR).formula,
            "(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))",
        )
        self.assertEqual(
            self.load_plural(TEST_HE_CUSTOM).formula,
            "(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 10) ? 2 : 3))",
        )
        self.assertEqual(self.load_plural(TEST_HE_SIMPLE).formula, "(n != 1)")
        self.assertEqual(
            self.load_plural(TEST_HE_THREE).formula, "n==1 ? 0 : n==2 ? 2 : 1"
        )

    def test_msgmerge(self):
        test_file = os.path.join(self.tempdir, "test.po")
        with open(test_file, "w") as handle:
            handle.write("")

        # Test file content is updated
        self.FORMAT.update_bilingual(test_file, TEST_POT)
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)

        # Backup flag is not compatible with others
        with self.assertRaises(UpdateError):
            self.FORMAT.update_bilingual(test_file, TEST_POT, args=["--backup=none"])
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)

        # Test warning in ouput (used Unicode POT file without charset specified)
        with self.assertRaises(UpdateError):
            self.FORMAT.update_bilingual(test_file, TEST_POT_UNICODE)
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)


class PropertiesFormatTest(AutoFormatTest):
    FORMAT = PropertiesFormat
    FILE = TEST_PROPERTIES
    MIME = "text/plain"
    COUNT = 12
    EXT = "properties"
    MASK = "java/swing_messages_*.properties"
    EXPECTED_PATH = "java/swing_messages_cs-CZ.properties"
    FIND = "IGNORE"
    FIND_CONTEXT = "IGNORE"
    FIND_MATCH = "Ignore"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            (newdata).strip().splitlines(),
            (testdata).strip().splitlines(),
        )


class GWTFormatTest(AutoFormatTest):
    FORMAT = GWTFormat
    FILE = TEST_GWT
    MIME = "text/plain"
    COUNT = 1
    EXT = "properties"
    MASK = "gwt/gwt_*.properties"
    EXPECTED_PATH = "gwt/gwt_cs-CZ.properties"
    FIND = "cartItems"
    FIND_CONTEXT = "cartItems"
    FIND_MATCH = "There are {0,number} items in your cart."
    EDIT_TARGET = [
        "There are {0,number} goods in your cart.",
        "There is {0,number} good in your cart.",
    ]
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    BASE = ""
    MONOLINGUAL = True

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            (newdata).strip().splitlines(),
            (testdata).strip().splitlines(),
        )


class JoomlaFormatTest(AutoFormatTest):
    FORMAT = JoomlaFormat
    FILE = TEST_JOOMLA
    MIME = "text/plain"
    COUNT = 4
    EXT = "ini"
    MASK = "joomla/*.ini"
    EXPECTED_PATH = "joomla/cs_CZ.ini"
    MATCH = "\n"
    FIND = "HELLO"
    FIND_CONTEXT = "HELLO"
    FIND_MATCH = 'Ahoj "světe"!\n'
    NEW_UNIT_MATCH = b'\nkey="Source string"\n'
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class JSONFormatTest(AutoFormatTest):
    FORMAT = JSONFormat
    FILE = TEST_JSON
    MIME = "application/json"
    COUNT = 4
    EXT = "json"
    MASK = "json/*.json"
    EXPECTED_PATH = "json/cs_CZ.json"
    MATCH = "{}\n"
    BASE = ""
    NEW_UNIT_MATCH = b'\n    "Source string": ""\n'
    EXPECTED_FLAGS = ""

    def assert_same(self, newdata, testdata):
        self.assertJSONEqual(newdata.decode(), testdata.decode())


class JSONNestedFormatTest(JSONFormatTest):
    FORMAT = JSONNestedFormat
    FILE = TEST_NESTED_JSON
    COUNT = 4
    MASK = "json-nested/*.json"
    EXPECTED_PATH = "json-nested/cs_CZ.json"
    FIND_CONTEXT = "weblate.hello"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True
    NEW_UNIT_MATCH = b'\n    "key": "Source string"\n'


class WebExtesionJSONFormatTest(JSONFormatTest):
    FORMAT = WebExtensionJSONFormat
    FILE = TEST_WEBEXT_JSON
    COUNT = 4
    MASK = "webextension/_locales/*/messages.json"
    EXPECTED_PATH = "webextension/_locales/cs_CZ/messages.json"
    FIND_CONTEXT = "hello"
    NEW_UNIT_MATCH = b'\n    "key": {\n        "message": "Source string"\n    }\n'
    EXPECTED_FLAGS = "placeholders:$URL$"
    MONOLINGUAL = True


class PhpFormatTest(AutoFormatTest):
    FORMAT = PhpFormat
    FILE = TEST_PHP
    MIME = "text/x-php"
    COUNT = 4
    EXT = "php"
    MASK = "php/*/admin.php"
    EXPECTED_PATH = "php/cs_CZ/admin.php"
    MATCH = "<?php\n"
    FIND = "$LANG['foo']"
    FIND_CONTEXT = "$LANG['foo']"
    FIND_MATCH = "bar"
    BASE = ""
    NEW_UNIT_MATCH = b"\n$key = 'Source string';\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class LaravelPhpFormatTest(PhpFormatTest):
    FORMAT = LaravelPhpFormat
    FILE = TEST_LARAVEL
    FIND = "return[]->'apples'"
    FIND_CONTEXT = "return[]->'apples'"
    FIND_MATCH = "There is one apple\x1e\x1eThere are many apples"
    COUNT = 2


class AndroidFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = AndroidFormat
    FILE = TEST_ANDROID
    MIME = "application/xml"
    EXT = "xml"
    COUNT = 1
    MATCH = "<resources></resources>"
    MASK = "res/values-*/strings.xml"
    EXPECTED_PATH = "res/values-cs-rCZ/strings.xml"
    FIND = "Hello, world!\n"
    FIND_CONTEXT = "hello"
    FIND_MATCH = "Hello, world!\n"
    BASE = ""
    NEW_UNIT_MATCH = b'<string name="key">Source string</string>'
    MONOLINGUAL = True

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, self.FORMAT.get_language_code("sr_Latn")
            ),
            "res/values-b+sr+Latn/strings.xml",
        )


class XliffFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = XliffFormat
    FILE = TEST_XLIFF
    BASE = TEST_XLIFF
    MIME = "application/x-xliff"
    EXT = "xlf"
    COUNT = 4
    MATCH = '<file target-language="cs">'
    FIND_MATCH = ""
    MASK = "loc/*/default.xliff"
    EXPECTED_PATH = "loc/cs-CZ/default.xliff"
    NEW_UNIT_MATCH = (
        b'<trans-unit xml:space="preserve" id="key" approved="no">',
        b"<source>Source string</source>",
    )

    def test_set_state(self):
        # Read test content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, f"test.{self.EXT}")

        # Write test data to file
        with open(testfile, "wb") as handle:
            handle.write(testdata)

        # Update first unit as translated
        storage = self.parse_file(testfile)
        unit = storage.all_units[0]
        unit.set_target("test")
        unit.set_state(STATE_TRANSLATED)
        storage.save()

        # Verify the state is set
        with open(testfile) as handle:
            self.assertIn("<target>test</target>", handle.read())

        # Update first unit as fuzzy
        storage = self.parse_file(testfile)
        unit = storage.all_units[0]
        unit.set_target("test")
        unit.set_state(STATE_FUZZY)
        storage.save()

        # Verify the state is set
        with open(testfile) as handle:
            self.assertIn(
                '<target state="needs-translation">test</target>', handle.read()
            )


class XliffIdFormatTest(XliffFormatTest):
    FILE = TEST_XLIFF_ID
    BASE = TEST_XLIFF_ID
    FIND_CONTEXT = "hello"
    EXPECTED_FLAGS = ""
    COUNT = 5

    def test_edit_xliff(self):
        with open(get_test_file("ids-translated.xliff")) as handle:
            expected = handle.read()
        with open(get_test_file("ids-edited.xliff")) as handle:
            expected_template = handle.read()
        template_name = os.path.join(self.tempdir, "en.xliff")
        translated_name = os.path.join(self.tempdir, "cs.xliff")
        shutil.copy(self.FILE, template_name)
        shutil.copy(self.FILE, translated_name)
        template = self.FORMAT(template_name)
        source = self.FORMAT(template_name, template, is_template=True)
        translation = self.FORMAT(translated_name, template)

        unit = source.all_units[0]
        self.assertEqual(unit.source, "Hello, world!\n")
        self.assertEqual(unit.target, "Hello, world!\n")
        unit.set_target("Hello, wonderful world!\n")

        source.save()

        unit = translation.all_units[0]
        self.assertEqual(unit.source, "Hello, world!\n")
        self.assertEqual(unit.target, "")
        unit.set_target("Ahoj, svete!\n")

        unit = translation.all_units[1]
        self.assertEqual(
            unit.source, 'Orangutan has <x id="c" equiv-text="{{count}}"/> banana.\n'
        )
        self.assertEqual(unit.target, "")
        unit.set_target('Opicka ma <x id="c" equiv-text="{{count}}"/> banan.\n')

        self.assertEqual(len(translation.all_units), 5)
        self.assertTrue(translation.all_units[0].has_content())
        self.assertFalse(translation.all_units[0].is_readonly())
        self.assertTrue(translation.all_units[1].has_content())
        self.assertFalse(translation.all_units[1].is_readonly())
        self.assertTrue(translation.all_units[2].has_content())
        self.assertFalse(translation.all_units[2].is_readonly())
        self.assertTrue(translation.all_units[3].has_content())
        self.assertFalse(translation.all_units[3].is_readonly())
        self.assertFalse(translation.all_units[4].has_content())
        self.assertFalse(translation.all_units[4].is_readonly())

        translation.save()

        self.maxDiff = None
        with open(translated_name) as handle:
            self.assertXMLEqual(handle.read(), expected)

        with open(template_name) as handle:
            self.assertXMLEqual(handle.read(), expected_template)


class PoXliffFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = PoXliffFormat
    FILE = TEST_XLIFF
    BASE = TEST_XLIFF
    MIME = "application/x-xliff"
    EXT = "xlf"
    COUNT = 4
    MATCH = '<file target-language="cs">'
    FIND_MATCH = ""
    MASK = "loc/*/default.xliff"
    EXPECTED_PATH = "loc/cs-CZ/default.xliff"
    NEW_UNIT_MATCH = (
        b'<trans-unit xml:space="preserve" id="key" approved="no">',
        b"<source>Source string</source>",
    )


class PoXliffFormatTest2(PoXliffFormatTest):
    FILE = TEST_POXLIFF
    BASE = TEST_POXLIFF
    EXPECTED_FLAGS = (
        "c-format, font-family:ubuntu, font-size:22, font-weight:bold, max-size:100"
    )
    FIND_CONTEXT = "cs.po///2"
    COUNT = 5
    MATCH = '<file original="cs.po"'
    FIND_MATCH = "Ahoj světe!\n"


class RESXFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = RESXFormat
    FILE = TEST_RESX
    MIME = "text/microsoft-resx"
    EXT = "resx"
    COUNT = 4
    MASK = "resx/*.resx"
    EXPECTED_PATH = "resx/cs_CZ.resx"
    FIND = "Hello"
    FIND_CONTEXT = "Hello"
    FIND_MATCH = ""
    MATCH = "text/microsoft-resx"
    BASE = ""
    NEW_UNIT_MATCH = (
        b'<data name="key" xml:space="preserve">',
        b"<value>Source string</value>",
    )
    MONOLINGUAL = True


class YAMLFormatTest(AutoFormatTest):
    FORMAT = YAMLFormat
    FILE = TEST_YAML
    BASE = TEST_YAML
    MIME = "text/yaml"
    EXT = "yml"
    COUNT = 4
    MASK = "yaml/*.yml"
    EXPECTED_PATH = "yaml/cs_CZ.yml"
    FIND_CONTEXT = "weblate->hello"
    FIND_MATCH = ""
    MATCH = "weblate:"
    NEW_UNIT_MATCH = b"\nkey: Source string\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True

    def assert_same(self, newdata, testdata):
        # Fixup quotes as different translate toolkit versions behave
        # differently
        self.assertEqual(
            newdata.decode().replace("'", '"').strip().splitlines(),
            testdata.decode().strip().splitlines(),
        )


class RubyYAMLFormatTest(YAMLFormatTest):
    FORMAT = RubyYAMLFormat
    FILE = TEST_RUBY_YAML
    BASE = TEST_RUBY_YAML
    NEW_UNIT_MATCH = b"\n  key: Source string\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class TSFormatTest(XMLMixin, AutoFormatTest):
    FORMAT = TSFormat
    FILE = TEST_TS
    BASE = TEST_TS
    MIME = "application/x-linguist"
    EXT = "ts"
    COUNT = 4
    MASK = "ts/*.ts"
    EXPECTED_PATH = "ts/cs_CZ.ts"
    MATCH = '<TS version="2.0" language="cs">'
    FIND_MATCH = "Ahoj svete!\n"
    NEW_UNIT_MATCH = b"<source>Source string</source>"

    def assert_same(self, newdata, testdata):
        # Comparing of XML with doctype fails...
        newdata = newdata.replace(b"<!DOCTYPE TS>", b"")
        testdata = testdata.replace(b"<!DOCTYPE TS>", b"")
        super().assert_same(newdata, testdata)


class DTDFormatTest(AutoFormatTest):
    FORMAT = DTDFormat
    FILE = TEST_DTD
    BASE = TEST_DTD
    MIME = "application/xml-dtd"
    EXT = "dtd"
    COUNT = 4
    MASK = "dtd/*.dtd"
    EXPECTED_PATH = "dtd/cs_CZ.dtd"
    MATCH = "<!ENTITY"
    FIND_CONTEXT = "hello"
    FIND_MATCH = ""
    NEW_UNIT_MATCH = b'<!ENTITY key "Source string">'
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class CSVFormatTest(AutoFormatTest):
    FORMAT = CSVFormat
    FILE = TEST_CSV
    MIME = "text/csv"
    COUNT = 4
    EXT = "csv"
    MASK = "csv/*.csv"
    EXPECTED_PATH = "csv/cs_CZ.csv"
    MATCH = "HELLO"
    BASE = TEST_CSV
    FIND = "HELLO"
    FIND_MATCH = "Hello, world!\r\n"
    NEW_UNIT_MATCH = b'"Source string",""\r\n'
    EXPECTED_FLAGS = ""


class CSVFormatNoHeadTest(CSVFormatTest):
    FILE = TEST_CSV_NOHEAD
    COUNT = 1
    FIND = "Thank you for using Weblate."
    FIND_MATCH = "Děkujeme za použití Weblate."
    EXPECTED_FLAGS = ""
    NEW_UNIT_MATCH = b'"Source string",""\r\n'

    def test_save(self, edit=False):
        raise SkipTest("Saving currently adds field headers")


class CSVSimpleFormatNoHeadTest(CSVFormatNoHeadTest):
    FORMAT = CSVSimpleFormat
    EXPECTED_FLAGS = ""


class FlatXMLFormatTest(AutoFormatTest):
    FORMAT = FlatXMLFormat
    FILE = TEST_FLATXML
    MIME = "text/xml"
    COUNT = 2
    EXT = "xml"
    MASK = "xml/*.xml"
    BASE = TEST_FLATXML
    EXPECTED_PATH = "xml/cs_CZ.xml"
    MATCH = "hello"
    FIND = "Hello World!"
    FIND_CONTEXT = "hello_world"
    FIND_MATCH = "Hello World!"
    NEW_UNIT_MATCH = b'<str key="key">Source string</str>\n'
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class INIFormatTest(AutoFormatTest):
    FORMAT = INIFormat
    FILE = TEST_INI
    MIME = "text/plain"
    COUNT = 4
    BASE = ""
    EXT = "ini"
    MASK = "ini/*.ini"
    EXPECTED_PATH = "ini/cs_CZ.ini"
    MATCH = "\n"
    FIND = 'Ahoj "světe"!\\n'
    FIND_CONTEXT = "[weblate]hello"
    FIND_MATCH = 'Ahoj "světe"!\\n'
    NEW_UNIT_MATCH = b"\nkey = Source string"
    NEW_UNIT_KEY = "[test]key"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class InnoSetupINIFormatTest(INIFormatTest):
    FORMAT = InnoSetupINIFormat
    EXT = "islu"


class XWikiPropertiesFormatTest(PropertiesFormatTest):
    FORMAT = XWikiPropertiesFormat
    FILE = TEST_XWIKI_PROPERTIES
    BASE = ""
    MIME = "text/plain"
    COUNT = 10
    COUNT_CONTENT = 8
    EXT = "properties"
    MASK = "java/xwiki_*.properties"
    EXPECTED_PATH = "java/xwiki_cs-CZ.properties"
    FIND = "job.question.button.confirm"
    FIND_CONTEXT = "job.question.button.confirm"
    FIND_MATCH = "Confirm the operation {0}"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    EDIT_TARGET = "[{0}] تىپتىكى خىزمەتنى باشلاش"
    EDIT_OFFSET = 3

    def test_new_language(self):
        self.maxDiff = None
        out = os.path.join(self.tempdir, f"test_new_language.{self.EXT}")
        language = Language.objects.get(code="cs")
        self.FORMAT.add_language(out, language, self.BASE)
        template_storage = self.parse_file(self.FILE)
        new_language = self.FORMAT(out, template_storage, language.code)
        unit, add = new_language.find_unit("job.status.success")
        self.assertTrue(add)
        unit.set_target("Fait")
        new_language.add_unit(unit.unit)
        new_language.save()

        # Read new content
        with open(out) as handle:
            newdata = handle.read()

        with open(TEST_XWIKI_PROPERTIES_NEW_LANGUAGE) as handle:
            expected = handle.read()

        self.assertEqual(expected + "\n", newdata)


class XWikiPagePropertiesFormatTest(PropertiesFormatTest):
    FORMAT = XWikiPagePropertiesFormat
    FILE = TEST_XWIKI_PAGE_PROPERTIES
    SOURCE_FILE = TEST_XWIKI_PAGE_PROPERTIES_SOURCE
    BASE = ""
    MIME = "text/plain"
    COUNT = 6
    COUNT_CONTENT = 4
    EXT = "xml"
    MASK = "xml/XWikiSource.*.xml"
    EXPECTED_PATH = "xml/XWikiSource.cs.xml"
    FIND = "administration.section.users.disableUser.done"
    FIND_CONTEXT = "administration.section.users.disableUser.done"
    FIND_MATCH = "User account disabled"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, self.FORMAT.get_language_code("cs")
            ),
            self.EXPECTED_PATH,
        )

    def test_save(self, edit=False):
        self.maxDiff = None
        super().test_save(edit)

        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Read new content
        with open(testfile) as handle:
            newdata = handle.read()

        # Perform some general assertions about the copyright
        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn(
            "<!--\n"
            " * See the NOTICE file distributed with"
            " this work for additional",
            newdata,
        )
        self.assertIn(
            "* 02110-1301 USA, or see the FSF site: http://www.fsf.org.\n-->", newdata
        )
        # Remove XML declaration so that etree doesn't complain for parsing
        newdata = newdata.replace('<?xml version="1.1" encoding="UTF-8"?>', "")
        xml_data = etree.XML(newdata)
        self.assertEqual("1", xml_data.find("translation").text)
        self.assertIs(None, xml_data.find("attachment"))
        self.assertIs(None, xml_data.find("object"))

    def translate_unit(self, units, translation_data, index, target):
        unit_to_translate, create = translation_data.find_unit(
            units[index].context, units[index].source
        )
        self.assertTrue(create)
        translation_data.add_unit(unit_to_translate.unit)
        translation_data.all_units[index].unit = unit_to_translate.unit
        unit_to_translate.set_target(target)

    def test_translate_file(self):
        self.maxDiff = None
        # Parse test file
        storage = self.parse_file(self.SOURCE_FILE)
        units = storage.all_units

        # # Create appropriate target file
        translation_file = os.path.join(
            self.tempdir, os.path.basename(self.EXPECTED_PATH)
        )
        self.FORMAT.add_language(
            translation_file, Language.objects.get(code="fr"), self.BASE
        )
        translation_data = self.FORMAT(
            storefile=translation_file, template_store=storage, language_code="fr"
        )
        translation_units = translation_data.all_units
        self.assertEqual(self.COUNT, len(translation_units))

        self.translate_unit(
            units, translation_data, 1, "Erreur lors de la désactivation du compte."
        )
        expected_translation = (
            "L'utilisateur que vous êtes sur le point de "
            "supprimer est le dernier auteur de "
            "{0}{1,choice,1#1 page|1<{1} pages}{2}."
        )
        self.translate_unit(units, translation_data, 2, expected_translation)

        self.translate_unit(units, translation_data, 4, 'Si rempli à "Oui"...')

        # Save test file
        translation_data.save()

        # Read new content
        with open(translation_file, "rb") as handle:
            newdata = handle.read()

        # Read source file content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Check if content matches
        self.assert_same(testdata, newdata)


class XWikiFullPageFormatTest(AutoFormatTest):
    FORMAT = XWikiFullPageFormat
    FILE = TEST_XWIKI_FULL_PAGE
    SOURCE_FILE = TEST_XWIKI_FULL_PAGE_SOURCE
    BASE = ""
    MIME = "text/plain"
    COUNT = 2
    EXT = "xml"
    MASK = "xml/XWikiFullPage.*.xml"
    EXPECTED_PATH = "xml/XWikiFullPage.cs.xml"
    FIND = "title"
    FIND_CONTEXT = "title"
    FIND_MATCH = "Bac à sable"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    EDIT_TARGET = """= Titre=\n"
                "\n"
                "* [[Bac à sable>>Sandbox.TestPage1]]\n"
                "{{info}}\n"
                "Ne vous inquiétez pas d'écraser\n"
                "{{/info}}"
                [{0}] تىپتىكى خىزمەتنى باشلاش"""

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(
                self.MASK, self.FORMAT.get_language_code("cs")
            ),
            self.EXPECTED_PATH,
        )

    def test_new_unit(self):
        # This test does not make sense in this context, since we're not supposed
        # to be able to add new units.
        pass

    def test_save(self, edit=False):
        self.maxDiff = None
        super().test_save(edit)

        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Read new content
        with open(testfile) as handle:
            newdata = handle.read()

        # Perform some general assertions about the copyright
        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn(
            "<!--\n"
            " * See the NOTICE file distributed with"
            " this work for additional",
            newdata,
        )
        self.assertIn(
            "* 02110-1301 USA, or see the FSF site: http://www.fsf.org.\n" "-->",
            newdata,
        )
        # Remove XML declaration so that etree doesn't complain for parsing
        newdata = newdata.replace('<?xml version="1.1" encoding="UTF-8"?>', "")
        xml_data = etree.XML(newdata)
        self.assertEqual("1", xml_data.find("translation").text)
        self.assertIs(None, xml_data.find("attachment"))
        self.assertIs(None, xml_data.find("object"))

    def translate_unit(self, units, translation_data, index, target):
        unit_to_translate, create = translation_data.find_unit(
            units[index].context, units[index].source
        )
        self.assertTrue(create)
        translation_data.add_unit(unit_to_translate.unit)
        translation_data.all_units[index].unit = unit_to_translate.unit
        unit_to_translate.set_target(target)

    def test_translate_file(self):
        self.maxDiff = None
        # Parse test file
        storage = self.parse_file(self.SOURCE_FILE)
        units = storage.all_units

        # # Create appropriate target file
        translation_file = os.path.join(
            self.tempdir, os.path.basename(self.EXPECTED_PATH)
        )
        self.FORMAT.add_language(
            translation_file, Language.objects.get(code="it"), self.BASE
        )
        translation_data = self.FORMAT(
            storefile=translation_file, template_store=storage, language_code="it"
        )
        translation_units = translation_data.all_units
        self.assertEqual(self.COUNT, len(translation_units))

        expected_translation = (
            "L'area test o sandbox è una parte del wiki che si "
            "può modificare liberamente.\n\n{{info}}Non "
            "preoccupatevi >{{/info}}"
        )
        self.translate_unit(units, translation_data, 0, expected_translation)
        self.translate_unit(units, translation_data, 1, "Bac à sable")

        # Save test file
        translation_data.save()

        # Read new content
        with open(translation_file, "rb") as handle:
            newdata = handle.read()

        # Read source file content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Check if content matches
        self.assert_same(testdata, newdata)


class TBXFormatTest(AutoFormatTest):
    FORMAT = TBXFormat
    FILE = TEST_TBX
    BASE = ""
    MIME = "application/x-tbx"
    EXT = "tbx"
    COUNT = 4
    MASK = "tbx/*.tbx"
    EXPECTED_PATH = "tbx/cs_CZ.tbx"
    MATCH = "<martif"
    FIND = "address bar"
    FIND_MATCH = "adresní řádek"
    NEW_UNIT_MATCH = b"<term>Source string</term>"
    EXPECTED_FLAGS = ""
