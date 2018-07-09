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
"""Captcha tests"""

from unittest import TestCase

from django.core.exceptions import ValidationError

from weblate.accounts.password_validation import CharsPasswordValidator


class ValidationTest(TestCase):
    def validate(self, password):
        validator = CharsPasswordValidator()
        return validator.validate(password)

    def test_chars_good(self):
        self.assertIsNone(self.validate('123'))

    def test_chars_whitespace(self):
        self.assertRaises(
            ValidationError,
            self.validate,
            ' \r\n\t'
        )

    def test_chars_same(self):
        self.assertRaises(
            ValidationError,
            self.validate,
            'x' * 10
        )
