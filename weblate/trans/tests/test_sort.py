# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Unicode sorting."""

from django.test import TestCase

from weblate.trans.util import sort_choices


class SortTest(TestCase):
    def test_sort(self) -> None:
        result = sort_choices(((2, "zkouška"), (3, "zkouzka"), (1, "zkouaka")))
        self.assertEqual([1, 2, 3], [x[0] for x in result])
