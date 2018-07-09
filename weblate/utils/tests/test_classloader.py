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

from unittest import TestCase

from django.core.exceptions import ImproperlyConfigured

from six import assertRaisesRegex

from weblate.utils.classloader import load_class


class LoadClassTest(TestCase):
    def test_correct(self):
        cls = load_class('unittest.TestCase', 'TEST')
        self.assertEqual(cls, TestCase)

    def test_invalid_name(self):
        assertRaisesRegex(
            self,
            ImproperlyConfigured,
            'Error importing class unittest in TEST: .*"'
            '(not enough|need more than)',
            load_class, 'unittest', 'TEST'
        )

    def test_invalid_module(self):
        assertRaisesRegex(
            self,
            ImproperlyConfigured,
            'weblate.trans.tests.missing in TEST: "'
            'No module named .*missing["\']',
            load_class, 'weblate.trans.tests.missing.Foo', 'TEST'
        )

    def test_invalid_class(self):
        assertRaisesRegex(
            self,
            ImproperlyConfigured,
            '"weblate.utils.tests.test_classloader"'
            ' does not define a "Foo" class',
            load_class, 'weblate.utils.tests.test_classloader.Foo', 'TEST'
        )
