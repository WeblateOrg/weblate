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

from weblate.accounts.captcha import (
    hash_question, unhash_question, MathCaptcha
)


class CaptchaTest(TestCase):
    def test_decode(self):
        question = '1 + 1'
        timestamp = 1000
        hashed = hash_question(question, timestamp)
        self.assertEqual(
            (question, timestamp),
            unhash_question(hashed)
        )

    def test_tamper(self):
        hashed = hash_question('', 0) + '00'
        self.assertRaises(
            ValueError,
            unhash_question,
            hashed
        )

    def test_invalid(self):
        self.assertRaises(
            ValueError,
            unhash_question,
            ''
        )

    def test_object(self):
        captcha = MathCaptcha('1 * 2')
        self.assertFalse(
            captcha.validate(1)
        )
        self.assertTrue(
            captcha.validate(2)
        )
        restored = MathCaptcha.from_hash(captcha.hashed)
        self.assertEqual(
            captcha.question,
            restored.question
        )
        self.assertRaises(
            ValueError,
            MathCaptcha.from_hash,
            captcha.hashed[:40]
        )

    def test_generate(self):
        """Test generating of captcha for every operator."""
        captcha = MathCaptcha()
        for operator in MathCaptcha.operators:
            captcha.operators = (operator,)
            self.assertIn(operator, captcha.generate_question())
