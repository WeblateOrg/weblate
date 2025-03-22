# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.test import SimpleTestCase

from weblate.utils.similarity import Comparer


class ComparerTest(SimpleTestCase):
    def test_different(self) -> None:
        self.assertLessEqual(Comparer().similarity("a", "b"), 50)

    def test_same(self) -> None:
        self.assertEqual(Comparer().similarity("a", "a"), 100)

    def test_unicode(self) -> None:
        self.assertEqual(Comparer().similarity("NICHOLASŸ", "NICHOLAS"), 94)

    def test_emoji(self) -> None:
        self.assertEqual(Comparer().similarity("Weblate 😀", "Weblate 😍"), 88)
