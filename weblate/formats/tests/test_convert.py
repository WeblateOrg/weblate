#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import os
from tempfile import NamedTemporaryFile
from unittest import SkipTest

from weblate.formats.convert import (
    HTMLFormat,
    IDMLFormat,
    OpenDocumentFormat,
    PlainTextFormat,
    WindowsRCFormat,
)
from weblate.formats.helpers import BytesIOMode
from weblate.formats.tests.test_formats import AutoFormatTest
from weblate.trans.tests.utils import get_test_file
from weblate.utils.state import STATE_TRANSLATED

IDML_FILE = get_test_file("en.idml")
HTML_FILE = get_test_file("cs.html")
OPENDOCUMENT_FILE = get_test_file("cs.odt")
TEST_RC = get_test_file("cs-CZ.rc")
TEST_TXT = get_test_file("cs.txt")


class ConvertFormatTest(AutoFormatTest):
    NEW_UNIT_MATCH = None
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True

    CONVERT_TEMPLATE = ""
    CONVERT_TRANSLATION = ""
    CONVERT_EXPECTED = ""

    def test_convert(self):
        if not self.CONVERT_TEMPLATE:
            raise SkipTest(f"Test template not provided for {self.FORMAT.format_id}")
        template = NamedTemporaryFile(delete=False, mode="w+")
        translation = NamedTemporaryFile(delete=False, mode="w+")
        try:
            # Generate test files
            template.write(self.CONVERT_TEMPLATE)
            template.close()
            translation.write(self.CONVERT_TRANSLATION)
            translation.close()

            # Parse
            storage = self.FORMAT(
                translation.name,
                template_store=self.FORMAT(template.name, is_template=True),
            )

            # Ensure it is parsed correctly
            self.assertEqual(len(storage.content_units), 2)
            unit1, unit2 = storage.content_units
            self.assertEqual(unit1.source, "Hello")
            self.assertEqual(unit1.target, "Ahoj")
            self.assertEqual(unit2.source, "Bye")
            self.assertEqual(unit2.target, "")

            # Translation
            unit2.set_target("Nazdar")
            unit2.set_state(STATE_TRANSLATED)

            # Save
            storage.save()

            # Check translation
            with open(translation.name) as handle:
                self.assertEqual(handle.read(), self.CONVERT_EXPECTED)
        finally:
            os.unlink(template.name)
            os.unlink(translation.name)


class HTMLFormatTest(ConvertFormatTest):
    FORMAT = HTMLFormat
    FILE = HTML_FILE
    MIME = "text/html"
    EXT = "html"
    COUNT = 5
    MASK = "*/translations.html"
    EXPECTED_PATH = "cs_CZ/translations.html"
    FIND = "Orangutan has five bananas."
    FIND_MATCH = "Orangutan has five bananas."
    MATCH = b"<body>"
    NEW_UNIT_MATCH = None
    BASE = HTML_FILE
    EXPECTED_FLAGS = ""
    EDIT_OFFSET = 1

    CONVERT_TEMPLATE = "<html><body><p>Hello</p><p>Bye</p></body></html>"
    CONVERT_TRANSLATION = "<html><body><p>Ahoj</p><p></p></body></html>"
    CONVERT_EXPECTED = "<html><body><p>Ahoj</p><p>Nazdar</p></body></html>"


class OpenDocumentFormatTest(ConvertFormatTest):
    FORMAT = OpenDocumentFormat
    FILE = OPENDOCUMENT_FILE
    MIME = "application/vnd.oasis.opendocument.text"
    EXT = "odt"
    COUNT = 4
    MASK = "*/translations.odt"
    EXPECTED_PATH = "cs_CZ/translations.odt"
    FIND_CONTEXT = (
        "odf///office:document-content[0]/office:body[0]/office:text[0]/text:p[1]"
    )
    FIND_MATCH = "Orangutan has five bananas."
    MATCH = b"PK"
    NEW_UNIT_MATCH = None
    BASE = OPENDOCUMENT_FILE
    EXPECTED_FLAGS = ""
    EDIT_OFFSET = 1

    @staticmethod
    def extract_document(content):
        return bytes(
            OpenDocumentFormat.convertfile(BytesIOMode("test.odt", content), None)
        ).decode()

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            self.extract_document(newdata),
            self.extract_document(testdata),
        )


class IDMLFormatTest(ConvertFormatTest):
    FORMAT = IDMLFormat
    FILE = IDML_FILE
    MIME = "application/octet-stream"
    EXT = "idml"
    COUNT = 6
    MASK = "*/translations.idml"
    EXPECTED_PATH = "cs_CZ/translations.idml"
    FIND = """<g id="0"><g id="1">THE HEADLINE HERE</g></g>"""
    FIND_MATCH = """<g id="0"><g id="1">THE HEADLINE HERE</g></g>"""
    MATCH = b"PK"
    NEW_UNIT_MATCH = None
    BASE = IDML_FILE
    EXPECTED_FLAGS = ""
    EDIT_OFFSET = 1

    @staticmethod
    def extract_document(content):
        return bytes(
            IDMLFormat.convertfile(BytesIOMode("test.idml", content), None)
        ).decode()

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            self.extract_document(newdata),
            self.extract_document(testdata),
        )


class WindowsRCFormatTest(ConvertFormatTest):
    FORMAT = WindowsRCFormat
    FILE = TEST_RC
    BASE = TEST_RC
    MIME = "text/plain"
    EXT = "rc"
    COUNT = 5
    MASK = "rc/*.rc"
    EXPECTED_PATH = "rc/cs-CZ.rc"
    MATCH = "STRINGTABLE"
    FIND = "Hello, world!\n"
    FIND_MATCH = "Hello, world!\n"
    EDIT_OFFSET = 1

    CONVERT_TEMPLATE = """LANGUAGE LANG_ENGLISH, SUBLANG_DEFAULT

STRINGTABLE
BEGIN
    IDS_MSG1                "Hello"
    IDS_MSG2                "Bye"
END
"""
    CONVERT_TRANSLATION = """LANGUAGE LANG_CZECH, SUBLANG_DEFAULT

STRINGTABLE
BEGIN
    IDS_MSG1                "Ahoj"
END
"""
    CONVERT_EXPECTED = """LANGUAGE LANG_CZECH, SUBLANG_DEFAULT

STRINGTABLE
BEGIN
    IDS_MSG1                "Ahoj"
    IDS_MSG2                "Nazdar"
END
"""


class PlainTextFormatTest(ConvertFormatTest):
    FORMAT = PlainTextFormat
    FILE = TEST_TXT
    BASE = TEST_TXT
    MIME = "text/plain"
    EXT = "txt"
    COUNT = 5
    MASK = "txt/*.txt"
    EXPECTED_PATH = "txt/cs_CZ.txt"
    MATCH = "Hello"
    FIND = "Hello, world!"
    FIND_MATCH = "Hello, world!"
    EDIT_OFFSET = 1

    CONVERT_TEMPLATE = "Hello\n\nBye"
    CONVERT_TRANSLATION = "Ahoj\n\n"
    CONVERT_EXPECTED = "Ahoj\n\nNazdar"
