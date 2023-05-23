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

from weblate.trans.tests.utils import get_test_file
from weblate.trans.util import join_plural

from ..multi import MultiCSVUtf8Format
from .test_formats import AutoFormatTest

TEST_CSV = get_test_file("fr-multi.csv")
TEST_MONO_CSV = get_test_file("fr-multi-mono.csv")


class MultiCSVUtf8FormatTest(AutoFormatTest):
    FORMAT = MultiCSVUtf8Format
    FILE = TEST_CSV
    MIME = "text/csv"
    COUNT = 2
    EXT = "csv"
    MASK = "csv/*.csv"
    EXPECTED_PATH = "csv/cs_CZ.csv"
    MATCH = """\n"271681002","Stomach ache (finding)",""\n"""
    BASE = TEST_CSV
    FIND = "Myocardial infarction (disorder)"
    FIND_CONTEXT = "22298006"
    FIND_MATCH = join_plural(
        ("Infarctus myocardique", "Infarctus du myocarde", "Infarctus cardiaque")
    )
    NEW_UNIT_MATCH = b'"Source string",""\r\n'
    EXPECTED_FLAGS = ""
    EDIT_TARGET = ["Infarctus myocardique", "Infarctus du myocarde"]

    EXPECTED_EDIT = [
        '"context","source","target"',
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',
        '"271681002","Stomach ache (finding)","douleur à l\'estomac"',
        '"271681002","Stomach ache (finding)","douleur gastrique"',
    ]
    EXPECTED_ADD = [
        '"context","source","target"',
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',
        '"22298006","Myocardial infarction (disorder)","Infarctus myocardique"',
        '"271681002","Stomach ache (finding)","douleur à l\'estomac"',
        '"271681002","Stomach ache (finding)","douleur gastrique"',
        '"22298006","Myocardial infarction (disorder)","Infarctus du myocarde"',
    ]

    def assert_same(self, newdata, testdata):
        self.maxDiff = None
        self.assertEqual(testdata.decode().splitlines(), newdata.decode().splitlines())

    def test_edit(self):
        newdata = super().test_edit()
        self.maxDiff = None
        self.assertEqual(
            newdata.decode().splitlines(),
            self.EXPECTED_EDIT,
        )

    def test_edit_add(self):
        newdata = self.test_save(
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
    NEW_UNIT_MATCH = b'"key","Source string"\r\n'
    FILE = TEST_MONO_CSV
    EXPECTED_EDIT = [
        '"source","target"',
        '"22298006","Infarctus myocardique"',
        '"22298006","Infarctus du myocarde"',
        '"271681002","douleur à l\'estomac"',
        '"271681002","douleur gastrique"',
    ]
    EXPECTED_ADD = [
        '"source","target"',
        '"22298006","Infarctus myocardique"',
        '"22298006","Infarctus du myocarde"',
        '"22298006","Infarctus myocardique"',
        '"271681002","douleur à l\'estomac"',
        '"271681002","douleur gastrique"',
        '"22298006","Infarctus du myocarde"',
    ]
