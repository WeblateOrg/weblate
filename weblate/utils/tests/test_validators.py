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

from django.core.exceptions import ValidationError

from weblate.utils.validators import (
    validate_editor, clean_fullname, validate_fullname,
)


class EditorValidatorTest(TestCase):
    def test_empty(self):
        self.assertIsNone(validate_editor(''))

    def test_valid(self):
        self.assertIsNone(
            validate_editor('editor://open/?file=%(file)s&line=%(line)s')
        )

    def test_invalid_format(self):
        self.assertRaises(
            ValidationError,
            validate_editor,
            'editor://open/?file=%(fle)s&line=%(line)s'
        )

    def test_no_scheme(self):
        self.assertRaises(
            ValidationError,
            validate_editor,
            './local/url'
        )

    def test_invalid_scheme(self):
        self.assertRaises(
            ValidationError,
            validate_editor,
            'javascript:alert(0)'
        )
        self.assertRaises(
            ValidationError,
            validate_editor,
            'javaScript:alert(0)'
        )
        self.assertRaises(
            ValidationError,
            validate_editor,
            ' javaScript:alert(0)'
        )


class FullNameCleanTest(TestCase):
    def test_cleanup(self):
        self.assertEqual(
            'ahoj',
            clean_fullname('ahoj')
        )
        self.assertEqual(
            'ahojbar',
            clean_fullname('ahoj\x00bar')
        )

    def test_whitespace(self):
        self.assertEqual(
            'ahoj',
            clean_fullname(' ahoj ')
        )

    def test_none(self):
        self.assertEqual(
            None,
            clean_fullname(None),
        )

    def test_invalid(self):
        self.assertRaises(
            ValidationError,
            validate_fullname,
            'ahoj\x00bar'
        )
