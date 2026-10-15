# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx2
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from weblate.machinery.base import MachineTranslationError, UnsupportedLanguageError
from weblate.machinery.etranslation import (
    API_ROOT,
    DOMAINS_CACHE_SCOPE,
    ETranslation,
    callback_cache_key,
)
from weblate.machinery.forms import ETranslationMachineryForm
from weblate.machinery.models import validate_service_configuration

DOMAINS = {
    "GEN": {("EN", "FR"), ("EN", "DE")},
    "SPD": {("EN", "FR")},
}


@override_settings(ENABLE_HTTPS=True, SITE_DOMAIN="example.com")
class ETranslationTest(SimpleTestCase):
    def setUp(self) -> None:
        self.machine = ETranslation(
            {
                "key": "application",
                "secret": "password",
                "domain": "GEN",
                "component_domains": {"project/privacy-policy": "SPD"},
            }
        )
        self.unit = Mock()
        self.unit.translation.component.full_slug = "project/privacy-policy"

    @staticmethod
    def post_callback(url: str, payload: dict) -> int:
        request = RequestFactory().post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        match = resolve(request.path)
        return match.func(request, **match.kwargs).status_code

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_domains_and_languages(self, _get_domains: Mock) -> None:
        self.assertEqual(self.machine.get_domain(self.unit), "SPD")
        self.assertEqual(self.machine.get_domain(None), "GEN")
        self.assertIn(("EN", "DE"), self.machine.download_languages())
        self.assertNotEqual(
            self.machine.get_translation_cache_extra_parts(0, "Text", self.unit, 0),
            self.machine.get_translation_cache_extra_parts(0, "Text", None, 0),
        )

    def test_traditional_chinese_mapping(self) -> None:
        for code in ("zh_Hant", "zh_Hant_HK", "zh-Hant-HK", "zh_TW", "zh_HK"):
            with self.subTest(code=code):
                self.assertEqual(self.machine.map_language_code(code), "ZT")
        self.assertEqual(self.machine.map_language_code("zh_Hans_CN"), "ZH")
        self.assertEqual(self.machine.map_language_code("ca@valencia"), "CA")

    @patch.object(
        ETranslation,
        "get_domains",
        return_value={"GEN": {("EN", "ZH")}, "SPD": set()},
    )
    def test_traditional_chinese_does_not_fall_back_to_simplified(
        self, _get_domains: Mock
    ) -> None:
        for code in ("zh_Hant_HK", "zh_TW", "zh_HK"):
            with self.subTest(code=code):
                self.assertEqual(
                    list(self.machine.get_language_possibilities(Mock(code=code))),
                    ["ZT"],
                )
                with self.assertRaises(UnsupportedLanguageError):
                    self.machine.get_languages(Mock(code="en"), Mock(code=code))

    def test_domain_response_parsing(self) -> None:
        self.addCleanup(cache.delete, self.machine.get_cache_key(DOMAINS_CACHE_SCOPE))
        self.addCleanup(cache.delete, self.machine.languages_cache)
        response = Mock(
            json=lambda: [
                {
                    "domain": "GEN",
                    "languagePairs": [
                        "EN-FR-",
                        "EN-DE-",
                        "EN-CS-GLS",
                        "EN-IT-QE",
                        "EN-ES-LLM-GLS",
                        "EN-PL-UNKNOWN",
                    ],
                },
                {"domain": "SPD", "languagePairs": ["EN-FR-"]},
            ]
        )
        with patch.object(self.machine, "request", return_value=response) as request:
            domains = self.machine.get_domains()
        self.assertEqual(
            domains["GEN"],
            DOMAINS["GEN"]
            | {
                ("EN", "CS"),
                ("EN", "IT"),
                ("EN", "ES"),
            },
        )
        self.assertNotIn(("EN", "PL"), domains["GEN"])
        self.assertEqual(domains["SPD"], DOMAINS["SPD"])
        self.assertTrue(self.machine.is_supported("EN", "CS"))
        request.assert_called_once_with("get", f"{API_ROOT}/getDomains")

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_callback_before_submit_response(self, _get_domains: Mock) -> None:
        def submit(_method: str, _url: str, **kwargs: object) -> Mock:
            self.assertEqual(self.machine.get_auth(), ("application", "password"))
            payload = cast("dict[str, Any]", kwargs["json"])
            self.assertEqual(payload["domain"], "SPD")
            self.assertEqual(payload["sourceLanguage"], "EN")
            token = payload["callerInformation"]["externalReference"]
            status = self.post_callback(
                payload["notifications"]["success"]["http"],
                {
                    "requestId": 123,
                    "externalReference": token,
                    "targetLanguage": "FR",
                    "translatedText": "Bonjour",
                },
            )
            self.assertEqual(status, 200)
            return Mock(json=lambda: {"requestId": 123})

        with patch.object(self.machine, "request", side_effect=submit):
            result = list(
                self.machine.download_translations("EN", "FR", "Hello", self.unit, None)
            )
        self.assertEqual(result[0]["text"], "Bonjour")
        self.assertEqual(result[0]["quality"], 90)
        self.assertEqual(result[0]["origin"], "EU Formal Language (SPD)")

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_callback_after_submit_response(self, _get_domains: Mock) -> None:
        submitted: dict[str, Any] = {}

        def submit(_method: str, _url: str, **kwargs: object) -> Mock:
            payload = cast("dict[str, Any]", kwargs["json"])
            submitted.update(payload)
            return Mock(json=lambda: {"requestId": 123})

        def deliver(_seconds: float) -> None:
            token = submitted["callerInformation"]["externalReference"]
            self.assertEqual(
                self.post_callback(
                    submitted["notifications"]["success"]["http"],
                    {
                        "requestId": 123,
                        "externalReference": token,
                        "targetLanguage": "FR",
                        "translatedText": "Bonjour",
                    },
                ),
                200,
            )

        # Keep the real time module unchanged for background threads.
        with (
            patch.object(self.machine, "request", side_effect=submit),
            patch(
                "weblate.machinery.etranslation.time",
                wraps=time,
                sleep=Mock(side_effect=deliver),
            ),
        ):
            result = list(
                self.machine.download_translations("EN", "FR", "Hello", self.unit, None)
            )
        self.assertEqual(result[0]["text"], "Bonjour")

    @patch.object(ETranslation, "aget_domains", return_value=DOMAINS)
    def test_async_callback(self, _get_domains: Mock) -> None:
        submitted: dict[str, Any] = {}

        def submit(_method: str, _url: str, **kwargs: object) -> Mock:
            payload = cast("dict[str, Any]", kwargs["json"])
            submitted.update(payload)
            return Mock(json=lambda: {"requestId": 123})

        def deliver(_seconds: float) -> None:
            self.assertEqual(
                self.post_callback(
                    submitted["notifications"]["success"]["http"],
                    {
                        "requestId": 123,
                        "externalReference": submitted["callerInformation"][
                            "externalReference"
                        ],
                        "targetLanguage": "FR",
                        "translatedText": "Bonjour",
                    },
                ),
                200,
            )

        with (
            patch.object(self.machine, "arequest", side_effect=submit) as request,
            patch.object(self.machine, "request") as sync_request,
            patch(
                "weblate.machinery.etranslation.asyncio",
                wraps=asyncio,
                sleep=AsyncMock(side_effect=deliver),
            ),
        ):
            result = async_to_sync(self.machine.adownload_translations)(
                "EN", "FR", "Hello", self.unit, None
            )
        translation = next(iter(result))
        self.assertEqual(translation["text"], "Bonjour")
        request.assert_awaited_once()
        sync_request.assert_not_called()

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_failure_callback(self, _get_domains: Mock) -> None:
        def submit(_method: str, _url: str, **kwargs: object) -> Mock:
            payload = cast("dict[str, Any]", kwargs["json"])
            status = self.post_callback(
                payload["notifications"]["failure"]["http"],
                {
                    "requestId": 123,
                    "externalReference": payload["callerInformation"][
                        "externalReference"
                    ],
                    "targetLanguages": ["FR"],
                    "errorCode": -40005,
                    "errorMessage": "FACADE_INTERNAL_ERROR",
                },
            )
            self.assertEqual(status, 200)
            return Mock(json=lambda: {"requestId": 123})

        with (
            patch.object(self.machine, "request", side_effect=submit),
            self.assertRaisesRegex(
                MachineTranslationError,
                r"domain SPD: Internal processing error \(error code -40005\)",
            ),
        ):
            self.machine.download_translations("EN", "FR", "Hello", self.unit, None)

    def test_callback_preserves_unknown_error_message(self) -> None:
        token = uuid4()
        key = callback_cache_key(token.hex)
        self.addCleanup(cache.delete, key)
        cache.set(key, {"status": "pending", "target": "FR"}, 60)
        self.assertEqual(
            self.post_callback(
                reverse("etranslation-callback", args=[token]),
                {
                    "requestId": 123,
                    "externalReference": token.hex,
                    "targetLanguages": ["FR"],
                    "errorCode": -10702,
                    "errorMessage": "SAME_SOURCE_AND_TARGET_LANGUAGE",
                },
            ),
            200,
        )
        with self.assertRaisesRegex(
            MachineTranslationError, "Same source and target language"
        ):
            self.machine.callback_result(cache.get(key), "Hello", "GEN")

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_submit_error(self, _get_domains: Mock) -> None:
        response = httpx2.Response(
            400,
            json={"errorCode": -20013, "errorMessage": "UNSUPPORTED_LANGUAGE_PAIR"},
            request=httpx2.Request("POST", f"{API_ROOT}/askTranslate"),
        )
        error = httpx2.HTTPStatusError(
            "Bad Request", request=response.request, response=response
        )
        with (
            patch.object(self.machine, "request", side_effect=error),
            self.assertRaisesRegex(
                MachineTranslationError,
                r"domain SPD: The language pair is not supported by this domain "
                r"\(error code -20013\)",
            ),
        ):
            self.machine.download_translations("EN", "FR", "Hello", self.unit, None)

    @patch.object(ETranslation, "aget_domains", return_value=DOMAINS)
    def test_async_submit_error(self, _get_domains: Mock) -> None:
        response = httpx2.Response(
            400,
            json={"errorCode": -40005},
            request=httpx2.Request("POST", f"{API_ROOT}/askTranslate"),
        )
        error = httpx2.HTTPStatusError(
            "Bad Request", request=response.request, response=response
        )
        with (
            patch.object(self.machine, "arequest", side_effect=error),
            self.assertRaisesRegex(
                MachineTranslationError,
                r"domain SPD: Internal processing error \(error code -40005\)",
            ),
        ):
            async_to_sync(self.machine.adownload_translations)(
                "EN", "FR", "Hello", self.unit, None
            )

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_timeout(self, _get_domains: Mock) -> None:
        with (
            patch.object(
                self.machine,
                "request",
                return_value=Mock(json=lambda: {"requestId": 123}),
            ),
            patch("weblate.machinery.etranslation.CALLBACK_TIMEOUT", -1),
            self.assertRaisesRegex(MachineTranslationError, "Timed out"),
        ):
            self.machine.download_translations("EN", "FR", "Hello", self.unit, None)

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_unsupported_domain_pair_and_text_limit(self, _get_domains: Mock) -> None:
        with patch.object(self.machine, "request") as request:
            self.assertEqual(
                self.machine.download_translations(
                    "EN", "DE", "Hello", self.unit, None
                ),
                [],
            )
            self.assertEqual(
                self.machine.download_translations(
                    "EN", "FR", "x" * 5001, self.unit, None
                ),
                [],
            )
        request.assert_not_called()

    def test_callback_rejects_unknown_and_invalid_payload(self) -> None:
        token = uuid4()
        url = reverse("etranslation-callback", args=[token])
        payload = {
            "requestId": 123,
            "externalReference": token.hex,
            "targetLanguage": "FR",
            "translatedText": "Bonjour",
        }
        self.assertEqual(self.post_callback(url, payload), 404)
        key = callback_cache_key(token.hex)
        self.addCleanup(cache.delete, key)
        cache.set(key, {"status": "pending", "target": "FR"}, 60)
        payload["externalReference"] = uuid4().hex
        self.assertEqual(self.post_callback(url, payload), 400)
        payload["externalReference"] = token.hex
        payload["targetLanguage"] = "DE"
        self.assertEqual(self.post_callback(url, payload), 400)
        payload["targetLanguage"] = "FR"
        payload["requestId"] = True
        self.assertEqual(self.post_callback(url, payload), 400)
        payload["requestId"] = 123
        self.assertEqual(self.post_callback(url, payload), 200)
        self.assertEqual(self.post_callback(url, payload), 200)

    def test_callback_limits_body_without_content_length(self) -> None:
        token = uuid4()
        url = reverse("etranslation-callback", args=[token])
        request = RequestFactory().post(
            url, data=b"x" * 65537, content_type="application/json"
        )
        request.META.pop("CONTENT_LENGTH")
        match = resolve(request.path)
        with patch.object(request, "read", side_effect=AssertionError("body was read")):
            self.assertEqual(match.func(request, **match.kwargs).status_code, 404)

        key = callback_cache_key(token.hex)
        self.addCleanup(cache.delete, key)
        cache.set(key, {"status": "pending", "target": "FR"}, 60)
        self.assertEqual(match.func(request, **match.kwargs).status_code, 400)

    @patch.object(ETranslation, "get_domains", return_value=DOMAINS)
    def test_form_mapping_validation(self, _get_domains: Mock) -> None:
        data = {
            "key": "application",
            "secret": "password",
            "domain": "GEN",
            "component_domains": '{"project/privacy-policy": "spd"}',
        }
        form = ETranslationMachineryForm(ETranslation, data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["component_domains"], {"project/privacy-policy": "SPD"}
        )
        data["component_domains"] = '{"privacy-policy": "SPD"}'
        self.assertFalse(ETranslationMachineryForm(ETranslation, data).is_valid())

        for value in ("false", "0", "[]"):
            with self.subTest(value=value):
                data["component_domains"] = value
                invalid_form = ETranslationMachineryForm(ETranslation, data)
                self.assertFalse(invalid_form.is_valid())
                self.assertIn("component_domains", invalid_form.errors)

    def test_domain_choices_and_custom_code(self) -> None:
        form = ETranslationMachineryForm(
            ETranslation, initial={"domain": "QE", "key": "application"}
        )
        self.assertEqual(form["domain"].value(), form.OTHER_DOMAIN)
        self.assertEqual(form["other_domain"].value(), "QE")
        self.assertIn("General Text (GEN)", str(form["domain"]))

        data = {
            "key": "application",
            "secret": "password",
            "domain": form.OTHER_DOMAIN,
            "other_domain": "qe",
        }
        domains = {**DOMAINS, "QE": {("EN", "CS")}}
        with patch.object(ETranslation, "get_domains", return_value=domains):
            custom_form = ETranslationMachineryForm(ETranslation, data)
            self.assertTrue(custom_form.is_valid(), custom_form.errors)
        self.assertEqual(custom_form.cleaned_data["domain"], "QE")

        data["other_domain"] = "invalid code"
        invalid_form = ETranslationMachineryForm(ETranslation, data)
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("other_domain", invalid_form.errors)

    @patch.object(
        ETranslation,
        "get_domains",
        return_value={**DOMAINS, "QE": {("EN", "CS")}},
    )
    def test_custom_domain_service_configuration(self, _get_domains: Mock) -> None:
        service, configuration, errors = validate_service_configuration(
            "etranslation",
            json.dumps(
                {
                    "key": "application",
                    "secret": "password",
                    "domain": "_OTHER",
                    "other_domain": "qe",
                    "component_domains": '{"project/privacy-policy": "spd"}',
                }
            ),
        )
        self.assertIs(service, ETranslation)
        self.assertEqual(errors, [])
        self.assertEqual(configuration["domain"], "QE")
        self.assertNotIn("other_domain", configuration)
        self.assertEqual(
            configuration["component_domains"], {"project/privacy-policy": "SPD"}
        )
