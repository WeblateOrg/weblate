# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for XLIFF rich string."""

from django.test import TestCase
from translate.storage.placeables.strelem import StringElem
from translate.storage.xliff import xlifffile

from weblate.trans.tests.utils import get_test_file
from weblate.trans.util import rich_to_xliff_string, xliff_string_to_rich

TEST_X = get_test_file("placeholder-x.xliff")
TEST_MRK = get_test_file("placeholder-mrk.xliff")


class XliffPlaceholdersTest(TestCase):
    def test_bidirectional_xliff_string(self) -> None:
        cases = [
            'foo <x id="INTERPOLATION" equiv-text="{{ angular }}"/> bar',
            "",
            "hello world",
            "hello <p>world</p>",
        ]

        for string in cases:
            rich = xliff_string_to_rich(string)
            self.assertIsInstance(rich, list)
            self.assertIsInstance(rich[0], StringElem)

            final_string = rich_to_xliff_string(rich)
            self.assertEqual(string, final_string)

    def test_xliff_roundtrip(self) -> None:
        with open(TEST_X, "rb") as handle:
            source = handle.read()

        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual(
            'T: <x id="INTERPOLATION" equiv-text="{{ angular }}"/>', string
        )
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertXMLEqual(source.decode(), bytes(store).decode())

    def test_xliff_roundtrip_unknown(self) -> None:
        with open(TEST_MRK, "rb") as handle:
            source = handle.read()

        store = xlifffile.parsestring(source)
        string = rich_to_xliff_string(store.units[0].rich_source)
        self.assertEqual('T: <mrk mtype="protected">%s</mrk>', string)
        store.units[0].rich_source = xliff_string_to_rich(string)
        self.assertXMLEqual(source.decode(), bytes(store).decode())
