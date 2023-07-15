# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from weblate.utils.inv_regex import invert_re


class InvertRegexTest(TestCase):
    def test_basic(self):
        self.assertEqual(list(invert_re("a")), ["a"])

    def test_range(self):
        self.assertEqual(list(invert_re("[a-z]")), ["a"])

    def test_boundary(self):
        self.assertEqual(list(invert_re("^a$")), ["a"])

    def test_repeat(self):
        self.assertEqual(list(invert_re("a?")), [""])
        self.assertEqual(list(invert_re("a*")), [""])
        self.assertEqual(list(invert_re("a+")), ["a"])

    def test_broken(self):
        self.assertEqual(list(invert_re("(")), [])

    def test_question(self):
        self.assertEqual(list(invert_re("(?i)(^|\\W)via")), ["via", " via"])
