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

"""Test for fonts."""

from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.fonts import get_font
import weblate.utils.fonts


class FontsTest(SimpleTestCase):
    def setUp(self):
        # Always start with clear cache
        weblate.utils.fonts.FONT_CACHE = {}

    def tearDown(self):
        # Always reset cache
        weblate.utils.fonts.FONT_CACHE = {}

    def test_get(self):
        self.assertIsNotNone(get_font(12))
        self.assertIsNotNone(get_font(12, True))
        self.assertIsNotNone(get_font(12, False, False))
        self.assertIsNotNone(get_font(12))

    @override_settings(TTF_PATH='/nonexistent/')
    def test_get_missing(self):
        with self.assertRaises(IOError):
            get_font(12, True, False)
