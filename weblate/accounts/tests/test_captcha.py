# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Captcha tests."""

from unittest import TestCase

from weblate.accounts.captcha import MathCaptcha


class CaptchaTest(TestCase):
    def test_object(self) -> None:
        captcha = MathCaptcha("1 * 2")
        self.assertFalse(captcha.validate(1))
        self.assertTrue(captcha.validate(2))
        restored = MathCaptcha.unserialize(captcha.serialize())
        self.assertEqual(captcha.question, restored.question)
        self.assertTrue(restored.validate(2))

    def test_generate(self) -> None:
        """Test generating of captcha for every operator."""
        captcha = MathCaptcha()
        for operator in MathCaptcha.operators:
            captcha.operators = (operator,)
            self.assertIn(operator, captcha.generate_question())
