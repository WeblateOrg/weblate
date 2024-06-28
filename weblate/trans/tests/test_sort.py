# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Unicode sorting."""

from unittest import SkipTest

from django.test import TestCase

import weblate.trans.util


class SortTest(TestCase):
    def test_sort(self) -> None:
        if not weblate.trans.util.LOCALE_SETUP:
            raise SkipTest("Could not set up locales")
        result = weblate.trans.util.sort_choices(
            ((2, "zkouška"), (3, "zkouzka"), (1, "zkouaka"))
        )
        self.assertEqual([1, 2, 3], [x[0] for x in result])
