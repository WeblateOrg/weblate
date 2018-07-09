# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

"""
Tests for unicode sorting.
"""

from unittest import SkipTest

from django.test import TestCase

import weblate.trans.util


class SortTest(TestCase):
    def sort_tester(self):
        result = weblate.trans.util.sort_choices(
            ((2, 'zkouška'), (3, 'zkouzka'), (1, 'zkouaka'))
        )
        self.assertEqual(
            [1, 2, 3],
            [x[0] for x in result]
        )

    def test_sort_pyuca(self):
        if not weblate.trans.util.HAS_PYUCA:
            raise SkipTest('pyuca not installed')
        self.sort_tester()

    def test_sort_fallback(self):
        backup = weblate.trans.util.HAS_PYUCA
        try:
            weblate.trans.util.HAS_PYUCA = False

            self.sort_tester()
        finally:
            weblate.trans.util.HAS_PYUCA = backup
