# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

import os
from tempfile import NamedTemporaryFile

from weblate.checks.tests.test_checks import MockUnit
from weblate.formats.convert import (
    HTMLFormat,
    IDMLFormat,
    MarkdownFormat,
    OpenDocumentFormat,
    PlainTextFormat,
    WindowsRCFormat,
)
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.tests.test_formats import BaseFormatTest
from weblate.trans.tests.utils import get_test_file
from weblate.utils.state import STATE_TRANSLATED

IDML_FILE = get_test_file("en.idml")
HTML_FILE = get_test_file("cs.html")
MARKDOWN_FILE = get_test_file("cs.md")
OPENDOCUMENT_FILE = get_test_file("cs.odt")
TEST_RC = get_test_file("cs-CZ.rc")
TEST_TXT = get_test_file("cs.txt")


class ConvertFormatTest(BaseFormatTest):
    NEW_UNIT_MATCH = None
    EXPECTED_FLAGS = ""
    MONOLINGUAL = True

    CONVERT_TEMPLATE = ""
    CONVERT_TRANSLATION = ""
    CONVERT_EXPECTED = ""
    CONVERT_EXISTING: list[MockUnit] = []

    def test_convert(self) -> None:
        if not self.CONVERT_TEMPLATE:
            self.skipTest(
                f"Test template not provided for {self.format_class.format_id}"
            )
        translation = template = None
        try:
            # Generate test files
            with NamedTemporaryFile(delete=False, mode="w+") as template:
                template.write(self.CONVERT_TEMPLATE)
            with NamedTemporaryFile(delete=False, mode="w+") as translation:
                translation.write(self.CONVERT_TRANSLATION)

            # Parse
            storage = self.format_class(
                translation.name,
                template_store=self.format_class(template.name, is_template=True),
                existing_units=self.CONVERT_EXISTING,
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
            if template:
                os.unlink(template.name)
            if translation:
                os.unlink(translation.name)


class HTMLFormatTest(ConvertFormatTest):
    format_class = HTMLFormat
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


class MarkdownFormatTest(ConvertFormatTest):
    format_class = MarkdownFormat
    FILE = MARKDOWN_FILE
    MIME = "text/markdown"
    EXT = "md"
    COUNT = 5
    MASK = "*/translations.md"
    EXPECTED_PATH = "cs_CZ/translations.md"
    FIND = "Orangutan has five bananas."
    FIND_MATCH = ""
    MATCH = b"#"
    NEW_UNIT_MATCH = None
    BASE = MARKDOWN_FILE
    EXPECTED_FLAGS = ""
    EDIT_OFFSET = 1

    CONVERT_TEMPLATE = """# Hello

Bye
"""
    CONVERT_TRANSLATION = """# Ahoj
"""
    CONVERT_EXPECTED = """# Ahoj

Nazdar
"""
    CONVERT_EXISTING = [MockUnit(source="Hello", target="Ahoj")]

    def test_existing_units(self) -> None:
        with open(self.FILE, "rb") as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Write test data to file
        with open(testfile, "wb") as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.format_class(
            testfile,
            template_store=self.format_class(testfile, is_template=True),
            existing_units=[
                MockUnit(
                    source="Orangutan has five bananas.",
                    target="Orangutan má pět banánů.",
                )
            ],
        )

        # Save test file
        storage.save()

        # Read new content
        with open(testfile) as handle:
            newdata = handle.read()

        self.assertEqual(
            newdata,
            """# Ahoj světe!

Orangutan má pět banánů.

Try Weblate at [weblate.org](https://demo.weblate.org/)!

*Thank you for using Weblate.*
""",
        )


class OpenDocumentFormatTest(ConvertFormatTest):
    format_class = OpenDocumentFormat
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
            OpenDocumentFormat.convertfile(NamedBytesIO("test.odt", content), None)
        ).decode()

    def assert_same(self, newdata, testdata) -> None:
        self.assertEqual(
            self.extract_document(newdata),
            self.extract_document(testdata),
        )


class IDMLFormatTest(ConvertFormatTest):
    format_class = IDMLFormat
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
            IDMLFormat.convertfile(NamedBytesIO("test.idml", content), None)
        ).decode()

    def assert_same(self, newdata, testdata) -> None:
        self.assertEqual(
            self.extract_document(newdata),
            self.extract_document(testdata),
        )


class WindowsRCFormatTest(ConvertFormatTest):
    format_class = WindowsRCFormat
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
    format_class = PlainTextFormat
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
