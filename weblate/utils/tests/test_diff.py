# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.test import SimpleTestCase

from weblate.utils.diff import Differ


class DifferTestCase(SimpleTestCase):
    def setUp(self):
        self.differ = Differ()

    def test_basic(self):
        self.assertEqual(
            self.differ.highlight(
                "ahoj svete",
                "nazdar svete",
            ),
            "<del>nazdar</del><ins>ahoj</ins> svete",
        )
        self.assertEqual(
            self.differ.highlight(
                "nazdar svete",
                "ahoj svete",
            ),
            "<del>ahoj</del><ins>nazdar</ins> svete",
        )

    def test_chars(self):
        self.assertEqual(
            self.differ.highlight(
                "BXC",
                "AX",
            ),
            "<del>AX</del><ins>BXC</ins>",
        )
        self.assertEqual(
            self.differ.highlight(
                "AX",
                "BXC",
            ),
            "<del>BXC</del><ins>AX</ins>",
        )

    def test_hebrew(self):
        self.assertEqual(
            self.differ.highlight(
                "אָבוֹת קַדמוֹנִים כפולים של <אדם>",
                "אבות קדמונים כפולים של <אדם>",
            ),
            "<del>א</del><ins>אָ</ins>ב<del>ו</del><ins>וֹ</ins>ת <del>ק</del><ins>קַ</ins>דמו<del>נ</del><ins>ֹנִ</ins>ים כפולים של &lt;אדם&gt;",
        )
        self.assertEqual(
            self.differ.highlight(
                "אבות קדמונים כפולים של <אדם>",
                "אָבוֹת קַדמוֹנִים כפולים של <אדם>",
            ),
            "<ins>א</ins><del>אָ</del>ב<ins>ו</ins><del>וֹ</del>ת <ins>ק</ins><del>קַ</del>דמ<ins>ו</ins><del>וֹנִ</del><ins>נ</ins>ים כפולים של &lt;אדם&gt;",
        )
