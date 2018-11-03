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

from __future__ import unicode_literals

from unittest import TestCase

from weblate.utils.search import Comparer


class ComparerTest(TestCase):
    def test_different(self):
        self.assertLessEqual(
            Comparer().similarity('a', 'b'),
            50
        )

    def test_same(self):
        self.assertEqual(
            Comparer().similarity('a', 'a'),
            100
        )

    def test_unicode(self):
        self.assertEqual(
            Comparer().similarity('NICHOLASŸ', 'NICHOLAS'),
            88
        )

    def test_long(self):
        self.assertLessEqual(
            Comparer().similarity('a' * 200000, 'b' * 200000),
            50
        )
