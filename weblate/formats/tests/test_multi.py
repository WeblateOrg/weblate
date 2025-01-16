# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

from weblate.formats.multi import MultiCSVUtf8Format
from weblate.trans.tests.utils import get_test_file
from weblate.trans.util import join_plural

from .test_formats import BaseFormatTest

TEST_CSV = get_test_file("fr-multi.csv")
TEST_MONO_CSV = get_test_file("fr-multi-mono.csv")
TEST_MONO_BASE_CSV = get_test_file("en-multi.csv")


class MultiCSVUtf8FormatTest(BaseFormatTest):
    format_class = MultiCSVUtf8Format
    FILE = TEST_CSV
    MIME = "text/csv"
    COUNT = 2
    EXT = "csv"
    MASK = "csv/*.csv"
    EXPECTED_PATH = "csv/cs_CZ.csv"
    MATCH = """\n"271681002","Stomach ache (finding)",""\n"""
    BASE = TEST_CSV
    FIND = "Myocardial infarction (disorder)"  # codespell:ignore infarction
    FIND_CONTEXT = "22298006"
    FIND_MATCH = join_plural(
        ["Infarctus myocardique", "Infarctus du myocarde", "Infarctus cardiaque"]
    )
    NEW_UNIT_MATCH = b'"Source string",""\r\n'
    EXPECTED_FLAGS = ""
    EDIT_TARGET = ["Infarctus myocardique", "Infarctus du myocarde"]

    EXPECTED_EDIT = [
        '"context","source","target"',
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',  # codespell:ignore infarction
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',  # codespell:ignore infarction
        '"271681002","Stomach ache (finding)","douleur à l\'estomac"',
        '"271681002","Stomach ache (finding)","douleur gastrique"',
    ]
    EXPECTED_ADD = [
        '"context","source","target"',
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',  # codespell:ignore infarction
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',  # codespell:ignore infarction
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',  # codespell:ignore infarction
        '"271681002","Stomach ache (finding)","douleur à l\'estomac"',
        '"271681002","Stomach ache (finding)","douleur gastrique"',
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',  # codespell:ignore infarction
    ]

    def assert_same(self, newdata, testdata) -> None:
        self.maxDiff = None
        self.assertEqual(testdata.decode().splitlines(), newdata.decode().splitlines())

    def test_edit(self) -> None:
        newdata = super()._test_save(self.EDIT_TARGET)
        self.maxDiff = None
        self.assertEqual(
            newdata.decode().splitlines(),
            self.EXPECTED_EDIT,
        )

    def test_edit_add(self) -> None:
        newdata = self._test_save(
            [
                "Infarctus myocardique",
                "Infarctus du myocarde",
                "Infarctus myocardique",
                "Infarctus du myocarde",
            ]
        )
        self.maxDiff = None
        self.assertEqual(
            newdata.decode().splitlines(),
            self.EXPECTED_ADD,
        )


class MonoMultiCSVUtf8FormatTest(MultiCSVUtf8FormatTest):
    MONOLINGUAL = True
    FIND = ""
    MATCH = """\n"271681002","Stomach ache (finding)"\n"""
    NEW_UNIT_MATCH = b'"key","Source string"\r\n'
    COUNT = 3
    FILE = TEST_MONO_CSV
    BASE = TEST_MONO_BASE_CSV
    TEMPLATE = TEST_MONO_BASE_CSV
    SUPPORTS_NOTES = False
    EXPECTED_EDIT = [
        '"context","target"',
        '"22298006","Infarctus myocardique"',
        '"22298006","Infarctus du myocarde"',
        '"271681002","douleur à l\'estomac"',
        '"271681002","douleur gastrique"',
    ]
    EXPECTED_ADD = [
        '"context","target"',
        '"22298006","Infarctus myocardique"',
        '"22298006","Infarctus du myocarde"',
        '"22298006","Infarctus myocardique"',
        '"271681002","douleur à l\'estomac"',
        '"271681002","douleur gastrique"',
        '"22298006","Infarctus du myocarde"',
    ]
