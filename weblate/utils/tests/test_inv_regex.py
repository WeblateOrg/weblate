# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from weblate.utils.inv_regex import invert_re


class InvertRegexTest(TestCase):
    def test_basic(self) -> None:
        self.assertEqual(list(invert_re("a")), ["a"])

    def test_range(self) -> None:
        self.assertEqual(list(invert_re("[a-z]")), ["a"])

    def test_boundary(self) -> None:
        self.assertEqual(list(invert_re("^a$")), ["a"])

    def test_repeat(self) -> None:
        self.assertEqual(list(invert_re("a?")), [""])
        self.assertEqual(list(invert_re("a*")), [""])
        self.assertEqual(list(invert_re("a+")), ["a"])

    def test_broken(self) -> None:
        self.assertEqual(list(invert_re("(")), [])

    def test_question(self) -> None:
        self.assertEqual(list(invert_re("(?i)(^|\\W)via")), ["via", " via"])
