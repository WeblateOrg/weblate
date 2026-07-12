# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Captcha tests."""

import base64
import json
from unittest import TestCase

from django.http import HttpRequest
from django.test.utils import override_settings

from weblate.accounts.captcha import MathCaptcha, solve_altcha
from weblate.accounts.forms import CaptchaForm, CaptchaWidget


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
        ENABLE_HTTPS=True,
        ALTCHA_COST=1,
        ALTCHA_MEMORY_COST=8,
        ALTCHA_PARALLELISM=1,
    )
    def test_widget_challenge_serialization(self) -> None:
        request = HttpRequest()
        request.method = "GET"
        request.session = {}
        form = CaptchaForm(request=request)
        serialized = json.loads(CaptchaWidget.serialize_challenge(form.challenge))
        self.assertEqual(serialized["parameters"]["algorithm"], "ARGON2ID")
        self.assertEqual(serialized["parameters"]["cost"], 1)
        self.assertIn("signature", serialized)
        rendered = form["altcha"].as_widget()
        self.assertIn("<altcha-widget ", rendered)
        self.assertIn("challenge=", rendered)
        self.assertNotIn("challengejson=", rendered)
        media = str(form.media)
        self.assertIn('src="/static/js/vendor/altcha.js"', media)
        self.assertNotIn("data-cfasync", media)
        self.assertIn(" defer", media)

    @override_settings(REGISTRATION_CAPTCHA=False, ENABLE_HTTPS=True)
    def test_hidden_widget_has_no_media(self) -> None:
        request = HttpRequest()
        request.method = "GET"
        request.session = {}

        form = CaptchaForm(request=request)

        self.assertNotIn("altcha.js", str(form.media))

    @override_settings(
        REGISTRATION_CAPTCHA=True,
        ENABLE_HTTPS=True,
        ALTCHA_COST=1,
        ALTCHA_MEMORY_COST=8,
        ALTCHA_PARALLELISM=1,
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
                "altcha": solve_altcha(form.challenge, invalid=True),
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
            data={"captcha": -1, "altcha": solve_altcha(form.challenge, invalid=True)},
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

    @override_settings(
        REGISTRATION_CAPTCHA=True,
        ENABLE_HTTPS=True,
        ALTCHA_COST=1,
        ALTCHA_MEMORY_COST=8,
        ALTCHA_PARALLELISM=1,
    )
    def test_malformed_altcha_solution(self) -> None:
        def create_request(session):
            request = HttpRequest()
            request.method = "POST"
            request.session = session
            return request

        session_store = {}
        form = CaptchaForm(request=create_request(session_store))
        math = MathCaptcha.unserialize(session_store["captcha"])
        payload = json.loads(base64.b64decode(solve_altcha(form.challenge)).decode())
        payload["solution"]["counter"] = -1
        malformed_payload = base64.b64encode(json.dumps(payload).encode()).decode()

        form = CaptchaForm(
            request=create_request(session_store),
            data={"captcha": math.result, "altcha": malformed_payload},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Validation failed, please try again.", form.errors["altcha"])
        self.assertIn("captcha_challenge", session_store)
        self.assertIn("captcha", session_store)
