# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Captcha tests."""

from unittest import TestCase

from django.http import HttpRequest
from django.test.utils import override_settings

from weblate.accounts.captcha import MathCaptcha, solve_altcha
from weblate.accounts.forms import CaptchaForm


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

    @override_settings(
        REGISTRATION_CAPTCHA=True,
        ALTCHA_MAX_NUMBER=100,
    )
    def test_form(self) -> None:
        def create_request(session):
            request = HttpRequest()
            request.method = "POST"
            request.session = session
            return request

        session_store = {}

        # Successful submission
        form = CaptchaForm(request=create_request(session_store))
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        math = MathCaptcha.unserialize(session_store["captcha"])
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": math.result, "altcha": solve_altcha(form.challenge)},
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(session_store, {})

        # Wrong captcha
        form = CaptchaForm(request=create_request(session_store))
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": -1, "altcha": solve_altcha(form.challenge)},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        math = MathCaptcha.unserialize(session_store["captcha"])
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": math.result, "altcha": solve_altcha(form.challenge)},
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(session_store, {})

        # Wrong altcha
        form = CaptchaForm(request=create_request(session_store))
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        math = MathCaptcha.unserialize(session_store["captcha"])
        form = CaptchaForm(
            request=create_request(session_store),
            data={
                "captcha": math.result,
                "altcha": solve_altcha(form.challenge, number=-1),
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        math = MathCaptcha.unserialize(session_store["captcha"])
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": math.result, "altcha": solve_altcha(form.challenge)},
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(session_store, {})

        # Wrong both
        form = CaptchaForm(request=create_request(session_store))
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": -1, "altcha": solve_altcha(form.challenge, number=-1)},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
        math = MathCaptcha.unserialize(session_store["captcha"])
        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": math.result, "altcha": solve_altcha(form.challenge)},
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(session_store, {})
