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
Tests for special chars.
"""

from unittest import TestCase

from django.test.utils import override_settings

import six

from weblate.lang.models import Language
from weblate.trans.specialchars import get_special_chars


class SpecialCharsTest(TestCase):
    def test_af(self):
        chars = list(get_special_chars(Language(code='af')))
        self.assertEqual(len(chars), 10)

    def test_cs(self):
        chars = list(get_special_chars(Language(code='cs')))
        self.assertEqual(len(chars), 9)

    def test_brx(self):
        chars = list(get_special_chars(Language(code='brx')))
        self.assertEqual(len(chars), 9)

    def test_brx_add(self):
        chars = list(get_special_chars(Language(code='brx'), 'ahoj'))
        self.assertEqual(len(chars), 13)

    @override_settings(SPECIAL_CHARS=[six.unichr(x) for x in range(256)])
    def test_settings(self):
        chars = list(get_special_chars(Language(code='cs')))
        self.assertEqual(len(chars), 262)
