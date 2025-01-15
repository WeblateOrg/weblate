# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © WofWca <wofwca@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

from __future__ import annotations

import os.path
import shutil
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import NoReturn
from unittest import TestCase

from lxml import etree
from translate.storage.po import pofile

from weblate.formats.auto import AutodetectFormat, detect_filename, try_load
from weblate.formats.base import TranslationFormat, UpdateError
from weblate.formats.ttkit import (
    AndroidFormat,
    CSVFormat,
    CSVSimpleFormat,
    DTDFormat,
    FlatXMLFormat,
    FluentFormat,
    GoI18JSONFormat,
    GoI18V2JSONFormat,
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
    ResourceDictionaryFormat,
    RESXFormat,
    RichXliffFormat,
    RubyYAMLFormat,
    StringsdictFormat,
    TBXFormat,
    TSFormat,
    WebExtensionJSONFormat,
    XliffFormat,
    XWikiFullPageFormat,
    XWikiPagePropertiesFormat,
    XWikiPropertiesFormat,
    YAMLFormat,
)
from weblate.lang.data import PLURAL_UNKNOWN
from weblate.lang.models import Language, Plural
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import TempDirMixin, get_test_file
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, STATE_TRANSLATED

TEST_PO = get_test_file("cs.po")
TEST_CSV = get_test_file("cs-mono.csv")
TEST_CSV_NOHEAD = get_test_file("cs.csv")
TEST_FLATXML = get_test_file("cs-flat.xml")
TEST_RESOURCEDICTIONARY = get_test_file("cs.xaml")
TEST_JSON = get_test_file("cs.json")
TEST_GO18N_V1_JSON = get_test_file("cs-go18n-v1.json")
TEST_GO18N_V2_JSON = get_test_file("cs-go18n-v2.json")
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
TEST_STRINGSDICT = get_test_file("cs.stringsdict")
TEST_FLUENT = get_test_file("cs.ftl")


class AutoLoadTest(TestCase):
    def single_test(self, filename, fileclass) -> None:
        with open(filename, "rb") as handle:
            store = try_load(
                filename,
                handle.read(),
                None,
                None,
                is_template=fileclass.monolingual is None or fileclass.monolingual,
            )
            self.assertIsInstance(store, fileclass)
        self.assertEqual(fileclass, detect_filename(filename))

    def test_detect_android(self) -> None:
        self.assertEqual(AndroidFormat, detect_filename("foo/bar/strings_baz.xml"))

    def test_po(self) -> None:
        self.single_test(TEST_PO, PoFormat)
        self.single_test(TEST_POT, PoFormat)

    def test_json(self) -> None:
        self.single_test(TEST_JSON, JSONFormat)

    def test_php(self) -> None:
        self.single_test(TEST_PHP, PhpFormat)

    def test_properties(self) -> None:
        self.single_test(TEST_PROPERTIES, PropertiesFormat)

    def test_joomla(self) -> None:
        self.single_test(TEST_JOOMLA, JoomlaFormat)

    def test_android(self) -> None:
        self.single_test(TEST_ANDROID, AndroidFormat)

    def test_xliff(self) -> None:
        self.single_test(TEST_XLIFF, RichXliffFormat)

    def test_resx(self) -> None:
        self.single_test(TEST_RESX, RESXFormat)

    def test_yaml(self) -> None:
        self.single_test(TEST_YAML, YAMLFormat)

    def test_ruby_yaml(self) -> None:
        self.single_test(TEST_RUBY_YAML, RubyYAMLFormat)

    def test_content(self) -> None:
        """Test content based guess from ttkit."""
        with open(TEST_PO, "rb") as handle:
            data = handle.read()

        handle = BytesIO(data)
        store = AutodetectFormat(handle)
        self.assertIsInstance(store, AutodetectFormat)
        self.assertIsInstance(store.store, pofile)


class BaseFormatTest(FixtureTestCase, TempDirMixin, ABC):
    FILE = TEST_PO
    BASE = TEST_POT
    TEMPLATE = None
    MIME = "text/x-gettext-catalog"
    EXT = "po"
    COUNT = 4
    MATCH: str | bytes | None = "msgid_plural"
    MASK = "po/*.po"
    EXPECTED_PATH = "po/cs_CZ.po"
    FIND = "Hello, world!\n"
    FIND_CONTEXT = ""
    FIND_MATCH = "Ahoj světe!\n"
    NEW_UNIT_MATCH: str | bytes | tuple[bytes, ...] | tuple[str, ...] | None = (
        b'\nmsgctxt "key"\nmsgid "Source string"\n'
    )
    NEW_UNIT_KEY = "key"
    SUPPORTS_FLAG = True
    SUPPORTS_NOTES = True
    NOTE_FOR_TEST = "template note for test"
    EXPECTED_FLAGS: str | list[str] = "c-format, max-length:100"
    EDIT_OFFSET = 0
    EDIT_TARGET: str | list[str] = "Nazdar, svete!\n"
    MONOLINGUAL = False

    def setUp(self) -> None:
        super().setUp()
        self.create_temp()

    def tearDown(self) -> None:
        super().tearDown()
        self.remove_temp()

    @property
    @abstractmethod
    def format_class(self) -> TranslationFormat:
        raise NotImplementedError

    def parse_file(self, filename: str, template: str | None = None):
        if self.MONOLINGUAL:
            return self.format_class(
                filename,
                template_store=self.format_class(
                    template or self.TEMPLATE or filename, is_template=True
                ),
            )
        return self.format_class(filename)

    def test_parse(self) -> None:
        storage = self.parse_file(self.FILE)
        self.assertEqual(len(storage.all_units), self.COUNT)
        self.assertEqual(storage.mimetype(), self.MIME)
        self.assertEqual(storage.extension(), self.EXT)

    def _test_save(self, edit=None):
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
            units[self.EDIT_OFFSET].set_target(edit)

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
        return newdata

    def test_save(self) -> None:
        self._test_save()

    def test_edit(self) -> None:
        self._test_save(self.EDIT_TARGET)

    def assert_same(self, newdata, testdata) -> None:
        """
        Content aware comparison.

        This can be implemented in subclasses to implement content aware comparing of
        translation files.
        """
        self.maxDiff = None
        self.assertEqual(testdata.decode().strip(), newdata.decode().strip())

    def assert_no_notes(self, unit) -> None:
        """Assert that the underlying unit(s) do not have any notes."""
        if unit.unit:
            self.assertEqual(unit.unit.getnotes().strip(), "")
        else:
            # Assume this is a multi-unit. Will fail otherwise.
            for subunit in unit.units:
                self.assertEqual(subunit.unit.getnotes(), "")

    def test_find(self) -> None:
        storage = self.parse_file(self.FILE)
        unit, add = storage.find_unit(self.FIND_CONTEXT, self.FIND)
        self.assertFalse(add)
        if self.COUNT == 0:
            self.assertIsNone(unit)
        else:
            self.assertIsNotNone(unit)
            self.assertEqual(unit.target, self.FIND_MATCH)

    def test_add(self) -> None:
        self.assertTrue(self.format_class.is_valid_base_for_new(self.BASE, True))
        out = os.path.join(self.tempdir, f"test.{self.EXT}")
        self.format_class.add_language(out, Language.objects.get(code="cs"), self.BASE)
        self.parse_file(out)  # check the parser agrees that the new file is valid.
        if self.MATCH is None:
            self.assertTrue(os.path.isdir(out))
        else:
            mode = "rb" if isinstance(self.MATCH, bytes) else "r"
            with open(out, mode) as handle:
                data = handle.read()
            self.assertIn(self.MATCH, data)

    def test_get_language_filename(self) -> None:
        self.assertEqual(
            self.format_class.get_language_filename(
                self.MASK, self.format_class.get_language_code("cs_CZ")
            ),
            self.EXPECTED_PATH,
        )

    def test_new_unit(self) -> None:
        if not self.format_class.can_add_unit:
            self.skipTest("Not supported")
        # Read test content
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, f"test.{self.EXT}")

        # Write test data to file
        with open(testfile, "wb") as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile, template=testfile)
        if self.MONOLINGUAL:
            # Add to template for monolingual (it is the same file, just different object)
            storage = storage.template_store

        # Add new unit
        storage.new_unit(self.NEW_UNIT_KEY, "Source string")
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

    def test_flags(self) -> None:
        """
        Check flags on corresponding translatable units.

        If `EXPECTED_FLAGS` is a string instead of a list, check the first units.
        """
        units = self.parse_file(self.FILE).content_units
        if isinstance(self.EXPECTED_FLAGS, list):
            expected_list = self.EXPECTED_FLAGS
        else:
            expected_list = [self.EXPECTED_FLAGS]
        for i, expected_flag in enumerate(expected_list):
            unit = units[i]
            self.assertEqual(unit.flags, expected_flag)

    def test_add_monolingual(self) -> None:
        """
        Test for adding monolingual based on the template.

        This is used when Weblate is translating string not present in the translation
        in Translation.update_units().
        """
        if not self.MONOLINGUAL or not self.format_class.can_add_unit:
            self.skipTest("Not supported")

        temp_dir = Path(self.tempdir)
        template_file = temp_dir / f"test.tmpl.{self.EXT}"
        main_file = temp_dir / f"test.{self.EXT}"

        # Monolingual formats copy() template units when adding a translation.
        #
        # The use of copy() (instead of deepcopy()) can result in unintended
        # structural sharing for some formats (notably XML based formats that
        # store a DOM tree internally, e.g. AndroidFormat).
        #
        # This structural sharing can lead to mutations leaking back to the
        # template unit. In the context of this test, `removenotes()` leaks back
        # to the template.
        #
        # Unfortunately, we must accept this structural sharing for performance
        # reasons, see:
        # https://github.com/WeblateOrg/weblate/pull/11937#discussion_r1662166224
        # (a probably better alternative would be to fix and use
        # `buildFromUnit` in ttkit).
        #
        # It turns out, that in practice, the modifications from the structural
        # sharing do not actually impact Weblate's observable behavior.
        # This is likely because it round trips through files.
        #
        # We mimic the file round-tripping behavior in this test.

        # Create the template under test with a single string
        shutil.copy(self.FILE, template_file)
        template_storage = self.format_class(template_file, is_template=True)
        template_unit = template_storage.new_unit(self.NEW_UNIT_KEY, "Source string")
        if self.SUPPORTS_NOTES:
            template_unit.unit.addnote(self.NOTE_FOR_TEST)
        template_storage.save()

        template_content = template_file.read_text()

        # Add a new language and translate the new string.
        self.format_class.add_language(
            main_file, Language.objects.get(code="cs"), self.BASE
        )
        target_storage = self.parse_file(main_file, template=template_file)
        target_unit, add = target_storage.find_unit(self.NEW_UNIT_KEY, "Source string")
        self.assertTrue(add)

        # This is what Translation.update_units() does
        target_storage.add_unit(target_unit)
        target_unit.set_target("Translated string (CS)")
        # Note: Explanations are currently ignored by most of the formats
        target_unit.set_explanation("Explanation")
        target_unit.set_source_explanation("Source explanation")
        # The approved state is saved by a few formats
        target_unit.set_state(STATE_APPROVED)
        target_storage.save()

        # Eagerly check that the target unit does not have notes.
        # This is the point where checking that the template unit still has the
        # notes would potentially fail (depending on the exact format).
        self.assert_no_notes(target_unit)

        # Template should not change now
        template_storage.save()
        self.assertEqual(template_file.read_text(), template_content)

        # Reload the storage to check notes were correctly written.
        target_storage = self.parse_file(main_file, template=template_file)
        target_unit, add = target_storage.find_unit(self.NEW_UNIT_KEY, "Source string")
        self.assertFalse(add)
        self.assertEqual(target_unit.target, "Translated string (CS)")

        if self.SUPPORTS_NOTES:
            # Check we get the aggregated notes through the unit wrapper:
            # We always (additionally) display the template notes to the user
            # (if they are different from the target unit notes).
            self.assertEqual(target_unit.notes.strip(), self.NOTE_FOR_TEST)

        # Check there are no notes on the underlying unit.
        self.assert_no_notes(target_unit)


class XMLMixin:
    def assert_same(self, newdata, testdata) -> None:
        self.assertXMLEqual(newdata.decode(), testdata.decode())


class PoFormatTest(BaseFormatTest):
    format_class = PoFormat
    EDIT_OFFSET = 1

    def test_add_encoding(self) -> None:
        out = os.path.join(self.tempdir, "test.po")
        self.format_class.add_language(
            out, Language.objects.get(code="cs"), TEST_POT_UNICODE
        )
        with open(out) as handle:
            data = handle.read()
        self.assertIn("Michal Čihař", data)

    def load_plural(self, filename):
        with open(filename, "rb") as handle:
            store = self.parse_file(handle)
            return store.get_plural(Language.objects.get(code="he"), store)

    def test_plurals(self) -> None:
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

    def test_msgmerge(self) -> None:
        test_file = os.path.join(self.tempdir, "test.po")
        with open(test_file, "w") as handle:
            handle.write("")

        # Test file content is updated
        self.format_class.update_bilingual(test_file, TEST_POT)
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)

        # Backup flag is not compatible with others
        with self.assertRaises(UpdateError):
            self.format_class.update_bilingual(
                test_file, TEST_POT, args=["--backup=none"]
            )
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)

        # Test warning in output (used Unicode POT file without charset specified)
        with self.assertRaises(UpdateError):
            self.format_class.update_bilingual(test_file, TEST_POT_UNICODE)
        with open(test_file) as handle:
            self.assertEqual(len(handle.read()), 340)

    def test_obsolete(self) -> None:
        # Test adding unit matching obsolete one
        storage = self.format_class(TEST_PO)
        # Remove duplicate entry
        unit = storage.all_units[0]
        self.assertEqual(unit.source, "Hello, world!\n")
        storage.delete_unit(unit.unit)

        # Verify it is not present
        handle = BytesIO()
        storage.save_content(handle)
        content = handle.getvalue().decode()
        self.assertNotIn('\nmsgid "Hello, world!\\n"', content)

        # Add unit back, it should now overwrite obsolete one
        storage.add_unit(unit)

        # Verify it is properly added
        handle = BytesIO()
        storage.save_content(handle)
        content = handle.getvalue().decode()
        self.assertIn('\nmsgid "Hello, world!\\n"', content)
        self.assertNotIn('\n#~ msgid "Hello, world!\\n"', content)


class PropertiesFormatTest(BaseFormatTest):
    format_class: type[TranslationFormat] = PropertiesFormat
    FILE = TEST_PROPERTIES
    MIME = "text/plain"
    COUNT = 12
    EXT = "properties"
    MASK = "java/swing_messages_*.properties"
    EXPECTED_PATH = "java/swing_messages_cs_CZ.properties"
    FIND = "IGNORE"
    FIND_CONTEXT = "IGNORE"
    FIND_MATCH = "Ignore"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True

    def assert_same(self, newdata, testdata) -> None:
        self.assertEqual(
            (newdata).strip().splitlines(),
            (testdata).strip().splitlines(),
        )


class GWTFormatTest(BaseFormatTest):
    format_class = GWTFormat
    FILE = TEST_GWT
    MIME = "text/plain"
    COUNT = 1
    EXT = "properties"
    MASK = "gwt/gwt_*.properties"
    EXPECTED_PATH = "gwt/gwt_cs_CZ.properties"
    FIND = "cartItems"
    FIND_CONTEXT = "cartItems"
    FIND_MATCH = (
        "There is {0,number} item in your cart.\x1e\x1e"
        "There are {0,number} items in your cart."
    )
    EDIT_TARGET = [
        "There is {0,number} good in your cart.",
        "There are {0,number} goods in your cart.",
    ]
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    BASE = ""
    MONOLINGUAL = True

    # GWTFormat uses a proppluralunit under the hood which does not support
    # `removenotes()`.
    # https://github.com/translate/translate/blob/7ecba141b535572de75616ddb5f78afb41c2b7b2/translate/storage/properties.py#L578
    SUPPORTS_NOTES = False

    def assert_same(self, newdata, testdata) -> None:
        self.assertEqual(
            (newdata).strip().splitlines(),
            (testdata).strip().splitlines(),
        )


class JoomlaFormatTest(BaseFormatTest):
    format_class = JoomlaFormat
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


class JSONFormatTest(BaseFormatTest):
    format_class = JSONFormat
    FILE = TEST_JSON
    MIME = "application/json"
    COUNT = 4
    EXT = "json"
    MASK = "json/*.json"
    EXPECTED_PATH = "json/cs_CZ.json"
    MATCH = "{}\n"
    BASE = ""
    NEW_UNIT_MATCH = b'\n    "Source string": ""\n'
    EXPECTED_FLAGS: str | list[str] = ""

    def assert_same(self, newdata, testdata) -> None:
        self.assertJSONEqual(newdata.decode(), testdata.decode())


class JSONNestedFormatTest(JSONFormatTest):
    format_class = JSONNestedFormat
    FILE = TEST_NESTED_JSON
    COUNT = 4
    MASK = "json-nested/*.json"
    EXPECTED_PATH = "json-nested/cs_CZ.json"
    FIND_CONTEXT = "weblate.hello"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True
    NEW_UNIT_MATCH = b'\n    "key": "Source string"\n'
    SUPPORTS_NOTES = False


class WebExtesionJSONFormatTest(JSONFormatTest):
    format_class = WebExtensionJSONFormat
    FILE = TEST_WEBEXT_JSON
    COUNT = 4
    MASK = "webextension/_locales/*/messages.json"
    EXPECTED_PATH = "webextension/_locales/cs_CZ/messages.json"
    FIND_CONTEXT = "hello"
    NEW_UNIT_MATCH = b'\n    "key": {\n        "message": "Source string"\n    }\n'
    EXPECTED_FLAGS = [
        "placeholders:$URL$,case-insensitive",
        "placeholders:$COUNT$,case-insensitive",
    ]
    MONOLINGUAL = True


class GoI18NV1JSONFormatTest(JSONFormatTest):
    format_class = GoI18JSONFormat
    FILE = TEST_GO18N_V1_JSON
    COUNT = 4
    MASK = "go-i18n-json/*.json"
    EXPECTED_PATH = "go-i18n-json/cs_CZ.json"
    FIND_CONTEXT = "hello"
    MATCH = "[]\n"
    NEW_UNIT_MATCH = (
        b'{\n        "id": "key",\n        "translation": "Source string"\n    }\n'
    )
    MONOLINGUAL = True


class GoI18NV2JSONFormatTest(JSONFormatTest):
    format_class = GoI18V2JSONFormat
    FILE = TEST_GO18N_V2_JSON
    COUNT = 4
    MASK = "go-i18n-json-v2/*.json"
    EXPECTED_PATH = "go-i18n-json-v2/cs_CZ.json"
    FIND_CONTEXT = "hello"
    NEW_UNIT_MATCH = b'\n    "key": "Source string"\n'
    MONOLINGUAL = True


class PhpFormatTest(BaseFormatTest):
    format_class = PhpFormat
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
    NEW_UNIT_KEY = "$LANG['key']"
    NEW_UNIT_MATCH = b"\n$LANG['key'] = 'Source string';\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True
    NOTE_FOR_TEST = "// template note for test"


class LaravelPhpFormatTest(PhpFormatTest):
    format_class = LaravelPhpFormat
    FILE = TEST_LARAVEL
    FIND = "return[]->'apples'"
    FIND_CONTEXT = "return[]->'apples'"
    FIND_MATCH = "There is one apple\x1e\x1eThere are many apples"
    COUNT = 2


class AndroidFormatTest(XMLMixin, BaseFormatTest):
    format_class = AndroidFormat
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

    def test_get_language_filename(self) -> None:
        self.assertEqual(
            self.format_class.get_language_filename(
                self.MASK, self.format_class.get_language_code("sr_Latn")
            ),
            "res/values-b+sr+Latn/strings.xml",
        )


class XliffFormatTest(XMLMixin, BaseFormatTest):
    format_class = XliffFormat
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
    EXPECTED_FLAGS = "c-format, max-length:100"

    def test_set_state(self) -> None:
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
            self.assertIn('<target state="translated">test</target>', handle.read())

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


class RichXliffFormatTest(XliffFormatTest):
    format_class = RichXliffFormat
    EXPECTED_FLAGS = "c-format, max-length:100, xml-text"


class XliffIdFormatTest(RichXliffFormatTest):
    FILE = TEST_XLIFF_ID
    BASE = TEST_XLIFF_ID
    FIND_CONTEXT = "hello"
    EXPECTED_FLAGS = "xml-text"
    COUNT = 5

    def test_edit_xliff(self) -> None:
        with open(get_test_file("ids-translated.xliff")) as handle:
            expected = handle.read()
        with open(get_test_file("ids-edited.xliff")) as handle:
            expected_template = handle.read()
        template_name = os.path.join(self.tempdir, "en.xliff")
        translated_name = os.path.join(self.tempdir, "cs.xliff")
        shutil.copy(self.FILE, template_name)
        shutil.copy(self.FILE, translated_name)
        template = self.format_class(template_name)
        source = self.format_class(template_name, template, is_template=True)
        translation = self.format_class(translated_name, template)

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


class PoXliffFormatTest(XMLMixin, BaseFormatTest):
    format_class = PoXliffFormat
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
    EXPECTED_FLAGS = "c-format, max-length:100"


class PoXliffFormatTest2(PoXliffFormatTest):
    FILE = TEST_POXLIFF
    BASE = TEST_POXLIFF
    EXPECTED_FLAGS = (
        "c-format, font-family:ubuntu, font-size:22, font-weight:bold, max-size:100"
    )
    FIND_CONTEXT = "cs.po///2"
    COUNT = 4
    MATCH = '<file original="cs.po"'
    FIND_MATCH = "Ahoj světe!\n"


class RESXFormatTest(XMLMixin, BaseFormatTest):
    format_class = RESXFormat
    FILE = TEST_RESX
    MIME = "text/microsoft-resx"
    EXT = "resx"
    COUNT = 4
    MASK = "resx/*.resx"
    EXPECTED_PATH = "resx/cs-CZ.resx"
    FIND = "Hello"
    FIND_CONTEXT = "Hello"
    FIND_MATCH = "Hello, world!"
    MATCH = "text/microsoft-resx"
    BASE = ""
    NEW_UNIT_MATCH = (
        b'<data name="key" xml:space="preserve">',
        b"<value>Source string</value>",
    )
    MONOLINGUAL = True


class YAMLFormatTest(BaseFormatTest):
    format_class = YAMLFormat
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
    SUPPORTS_NOTES = False

    def assert_same(self, newdata, testdata) -> None:
        # Fixup quotes as different translate toolkit versions behave
        # differently
        self.assertEqual(
            newdata.decode().replace("'", '"').strip().splitlines(),
            testdata.decode().strip().splitlines(),
        )


class RubyYAMLFormatTest(YAMLFormatTest):
    format_class = RubyYAMLFormat
    FILE = TEST_RUBY_YAML
    BASE = TEST_RUBY_YAML
    NEW_UNIT_MATCH = b"\n  key: Source string\n"
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True


class TSFormatTest(XMLMixin, BaseFormatTest):
    format_class = TSFormat
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

    def assert_same(self, newdata, testdata) -> None:
        # Comparing of XML with doctype fails...
        newdata = newdata.replace(b"<!DOCTYPE TS>", b"")
        testdata = testdata.replace(b"<!DOCTYPE TS>", b"")
        super().assert_same(newdata, testdata)


class DTDFormatTest(BaseFormatTest):
    format_class = DTDFormat
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
    SUPPORTS_NOTES = False


class CSVFormatTest(BaseFormatTest):
    format_class = CSVFormat
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

    def _test_save(self, edit=False) -> NoReturn:
        self.skipTest("Saving currently adds field headers")


class CSVSimpleFormatNoHeadTest(CSVFormatNoHeadTest):
    format_class = CSVSimpleFormat
    EXPECTED_FLAGS = ""


class FlatXMLFormatTest(BaseFormatTest):
    format_class = FlatXMLFormat
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
    SUPPORTS_NOTES = False


class ResourceDictionaryFormatTest(BaseFormatTest):
    format_class = ResourceDictionaryFormat
    FILE = TEST_RESOURCEDICTIONARY
    MIME = "application/xaml+xml"
    COUNT = 2
    EXT = "xaml"
    MASK = "Languages/*.xaml"
    BASE = TEST_RESOURCEDICTIONARY
    EXPECTED_PATH = "Languages/cs-CZ.xaml"
    MATCH = "hello"
    FIND = "Hello World!"
    FIND_CONTEXT = "hello_world"
    FIND_MATCH = "Hello World!"
    NEW_UNIT_MATCH = b'<system:String x:Key="key">Source string</system:String>\n'
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True
    SUPPORTS_NOTES = False


class INIFormatTest(BaseFormatTest):
    format_class = INIFormat
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
    SUPPORTS_NOTES = False


class InnoSetupINIFormatTest(INIFormatTest):
    format_class = InnoSetupINIFormat
    EXT = "islu"


class XWikiPropertiesFormatTest(PropertiesFormatTest):
    format_class = XWikiPropertiesFormat
    FILE = TEST_XWIKI_PROPERTIES
    BASE = ""
    MIME = "text/plain"
    COUNT = 10
    COUNT_CONTENT = 8
    EXT = "properties"
    MASK = "java/xwiki_*.properties"
    EXPECTED_PATH = "java/xwiki_cs_CZ.properties"
    FIND = "job.question.button.confirm"
    FIND_CONTEXT = "job.question.button.confirm"
    FIND_MATCH = "Confirm the operation {0}"
    MATCH = "\n"
    NEW_UNIT_MATCH = b"\nkey=Source string\n"
    EXPECTED_FLAGS = ""
    EDIT_TARGET = "[{0}] تىپتىكى خىزمەتنى باشلاش"
    EDIT_OFFSET = 3

    def test_new_language(self) -> None:
        self.maxDiff = None
        out = os.path.join(self.tempdir, f"test_new_language.{self.EXT}")
        language = Language.objects.get(code="cs")
        self.format_class.add_language(out, language, self.BASE)
        template_storage = self.parse_file(self.FILE)
        new_language = self.format_class(out, template_storage, language.code)
        unit, add = new_language.find_unit("job.status.success", "")
        self.assertTrue(add)
        unit.set_target("Fait")
        new_language.add_unit(unit)
        new_language.save()

        # Read new content
        with open(out) as handle:
            newdata = handle.read()

        with open(TEST_XWIKI_PROPERTIES_NEW_LANGUAGE) as handle:
            expected = handle.read()

        self.assertEqual(expected + "\n", newdata)


class XWikiPagePropertiesFormatTest(XMLMixin, PropertiesFormatTest):
    format_class = XWikiPagePropertiesFormat
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

    def test_get_language_filename(self) -> None:
        self.assertEqual(
            self.format_class.get_language_filename(
                self.MASK, self.format_class.get_language_code("cs")
            ),
            self.EXPECTED_PATH,
        )

    def _test_save(self, edit=False) -> None:
        self.maxDiff = None
        super()._test_save(edit)

        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Read new content
        with open(testfile) as handle:
            newdata = handle.read()

        # Perform some general assertions about the copyright
        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn(
            "<!--\n * See the NOTICE file distributed with this work for additional",
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

    def translate_unit(self, units, translation_data, index, target) -> None:
        unit_to_translate, create = translation_data.find_unit(
            units[index].context, units[index].source
        )
        self.assertTrue(create)
        translation_data.add_unit(unit_to_translate)
        translation_data.all_units[index].unit = unit_to_translate.unit
        unit_to_translate.set_target(target)

    def test_translate_file(self) -> None:
        self.maxDiff = None
        # Parse test file
        storage = self.parse_file(self.SOURCE_FILE)
        units = storage.all_units

        # # Create appropriate target file
        translation_file = os.path.join(
            self.tempdir, os.path.basename(self.EXPECTED_PATH)
        )
        self.format_class.add_language(
            translation_file, Language.objects.get(code="fr"), self.BASE
        )
        translation_data = self.format_class(
            storefile=translation_file,
            template_store=storage.template_store,
            language_code="fr",
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


class XWikiFullPageFormatTest(XMLMixin, BaseFormatTest):
    format_class = XWikiFullPageFormat
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
    MONOLINGUAL = True
    EDIT_TARGET = """= Titre=\n"
                "\n"
                "* [[Bac à sable>>Sandbox.TestPage1]]\n"
                "{{info}}\n"
                "Ne vous inquiétez pas d'écraser\n"
                "{{/info}}"
                [{0}] تىپتىكى خىزمەتنى باشلاش"""

    def test_get_language_filename(self) -> None:
        self.assertEqual(
            self.format_class.get_language_filename(
                self.MASK, self.format_class.get_language_code("cs")
            ),
            self.EXPECTED_PATH,
        )

    def test_new_unit(self) -> None:
        # This test does not make sense in this context, since we're not supposed
        # to be able to add new units.
        pass

    def _test_save(self, edit=False) -> None:
        self.maxDiff = None
        super()._test_save(edit)

        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Read new content
        with open(testfile) as handle:
            newdata = handle.read()

        # Perform some general assertions about the copyright
        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn(
            "<!--\n * See the NOTICE file distributed with this work for additional",
            newdata,
        )
        self.assertIn(
            "* 02110-1301 USA, or see the FSF site: http://www.fsf.org.\n-->",
            newdata,
        )
        # Remove XML declaration so that etree doesn't complain for parsing
        newdata = newdata.replace('<?xml version="1.1" encoding="UTF-8"?>', "")
        xml_data = etree.XML(newdata)
        self.assertEqual("1", xml_data.find("translation").text)
        self.assertIs(None, xml_data.find("attachment"))
        self.assertIs(None, xml_data.find("object"))

    def translate_unit(self, units, translation_data, index, target) -> None:
        unit_to_translate, create = translation_data.find_unit(
            units[index].context, units[index].source
        )
        self.assertTrue(create)
        translation_data.add_unit(unit_to_translate)
        translation_data.all_units[index].unit = unit_to_translate.unit
        unit_to_translate.set_target(target)

    def test_translate_file(self) -> None:
        self.maxDiff = None
        # Parse test file
        storage = self.parse_file(self.SOURCE_FILE)
        units = storage.all_units

        # # Create appropriate target file
        translation_file = os.path.join(
            self.tempdir, os.path.basename(self.EXPECTED_PATH)
        )
        self.format_class.add_language(
            translation_file, Language.objects.get(code="it"), self.BASE
        )
        translation_data = self.format_class(
            storefile=translation_file,
            template_store=storage.template_store,
            language_code="it",
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


class TBXFormatTest(XMLMixin, BaseFormatTest):
    format_class = TBXFormat
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


class StringsdictFormatTest(XMLMixin, BaseFormatTest):
    format_class = StringsdictFormat
    FILE = TEST_STRINGSDICT
    MIME = "application/xml"
    EXT = "stringsdict"
    COUNT = 1
    MATCH = '<plist version="1.0">'
    MASK = "Resources/*.lproj/Localizable.stringsdict"
    EXPECTED_PATH = "Resources/cs_CZ.lproj/Localizable.stringsdict"
    FIND = "Hello, world!\n"
    FIND_CONTEXT = "hello"
    FIND_MATCH = "Hello, world!\n"
    BASE = ""
    NEW_UNIT_MATCH = b"<string>Source string</string>"
    MONOLINGUAL = True
    EXPECTED_FLAGS = ""
    SUPPORTS_NOTES = False

    def test_get_plural(self) -> None:
        # Use up-to-date languages database and not the one from fixture
        Language.objects.all().delete()
        Language.objects.setup(update=False)

        # Create a storage class
        storage = self.parse_file(self.FILE)

        # Try getting plural with zero for all languages
        for language in Language.objects.iterator():
            plural = storage.get_plural(language, storage)
            self.assertIsInstance(plural, Plural)
            self.assertNotEqual(
                plural.type,
                PLURAL_UNKNOWN,
                f"Invalid plural type for {language.code}: {plural.formula}",
            )
            self.assertEqual(
                plural.get_plural_name(0),
                "Zero",
                f"Invalid plural name for {language.code}: {plural.formula}",
            )


class FluentFormatTest(BaseFormatTest):
    format_class = FluentFormat
    FILE = TEST_FLUENT
    MIME = "text/x-fluent"
    EXT = "ftl"
    COUNT = 4
    MATCH = ""
    MASK = "locales/*/messages.ftl"
    EXPECTED_PATH = "locales/cs_CZ/messages.ftl"
    BASE = ""
    FIND = 'Ahoj "světe"!\\n'
    FIND_CONTEXT = "hello"
    FIND_MATCH = 'Ahoj "světe"!\\n'
    NEW_UNIT_MATCH = b"\nkey = Source string"
    MONOLINGUAL = True
    EXPECTED_FLAGS = "fluent-type:Message"
