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
            self.differ.highlight("ahoj svete", "nazdar svete"),
            "<del>nazdar</del><ins>ahoj</ins> svete",
        )

    def test_chars(self):
        self.assertEqual(
            self.differ.highlight("BXC", "AX"), "<del>AX</del><ins>BXC</ins>"
        )
