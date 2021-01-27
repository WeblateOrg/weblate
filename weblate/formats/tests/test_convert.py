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

from weblate.formats.convert import (
    HTMLFormat,
    IDMLFormat,
    OpenDocumentFormat,
    WindowsRCFormat,
)
from weblate.formats.helpers import BytesIOMode
from weblate.formats.tests.test_formats import AutoFormatTest
from weblate.trans.tests.utils import get_test_file

IDML_FILE = get_test_file("en.idml")
HTML_FILE = get_test_file("cs.html")
OPENDOCUMENT_FILE = get_test_file("cs.odt")
TEST_RC = get_test_file("cs-CZ.rc")


class ConvertFormatTest(AutoFormatTest):
    NEW_UNIT_MATCH = None
    EXPECTED_FLAGS = ""

    def parse_file(self, filename):
        return self.FORMAT(filename, template_store=self.FORMAT(filename))


class HTMLFormatTest(ConvertFormatTest):
    FORMAT = HTMLFormat
    FILE = HTML_FILE
    MIME = "text/html"
    EXT = "html"
    COUNT = 5
    MASK = "*/translations.html"
    EXPECTED_PATH = "cs_CZ/translations.html"
    FIND_CONTEXT = "+html.body.p:5-1"
    FIND_MATCH = "Orangutan has five bananas."
    MATCH = b"<body>"
    NEW_UNIT_MATCH = None
    BASE = HTML_FILE
    EXPECTED_FLAGS = ""
    EDIT_OFFSET = 1


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
    FIND_CONTEXT = (
        "idPkg:Story[0]/{}Story[0]/{}XMLElement[0]/{}ParagraphStyleRange[0]"
        "Stories/Story_mainmainmainmainmainmainmainmainmainmainmainu188.xml"
    )
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
    FIND_CONTEXT = "STRINGTABLE.IDS_MSG1"
    FIND_MATCH = "Hello, world!\n"
    EDIT_OFFSET = 1
