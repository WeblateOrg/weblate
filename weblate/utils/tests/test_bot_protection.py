# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import time
from concurrent.futures import ThreadPoolExecutor
from inspect import isawaitable
from ipaddress import ip_network
from typing import TYPE_CHECKING
from unittest import skipUnless
from unittest.mock import Mock, patch

from altcha import Payload, create_challenge, solve_challenge
from altcha.v2 import derive_key_sha
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import include, path, resolve, reverse
from django.utils.translation import get_language

from weblate.auth.models import User
from weblate.oidc.urls import urlpatterns as oidc_patterns
from weblate.urls import real_patterns
from weblate.utils.bot_protection import (
    FEATURE_TIPS,
    BotProtectionMiddleware,
    binding,
    challenge_page,
    check_clearance,
    clearance,
    record_outcome,
    safe_target,
    secret,
    verification_stats,
    verify,
)

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIRequest


@override_settings(
    BOT_PROTECTION_ENABLED=True,
    BOT_PROTECTION_DIFFICULTY=1,
    URL_PREFIX="",
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ProofTest(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        cache.clear()

    def request(self, request_path: str = "/", **kwargs: str) -> WSGIRequest:
        request = self.factory.get(request_path, HTTP_ACCEPT="text/html")
        request.META.update(kwargs)
        request.__dict__["_dont_enforce_csrf_checks"] = True
        request.session = SessionStore()
        return request

    def solution(self, request: HttpRequest) -> dict:
        challenge = create_challenge(
            "SHA-256",
            1,
            key_prefix="0",
            expires_at=int(time.time()) + 300,
            data={"ip": binding(request), "target": "/?a=1&b=2", "v": 1},
            hmac_secret=secret(request),
        )
        solution = solve_challenge(challenge)
        assert solution is not None
        return Payload(challenge, solution).to_dict()

    def redeem(self, payload: object) -> HttpResponse:
        request = self.factory.post(
            "/-/pow/verify/", json.dumps(payload), content_type="application/json"
        )
        request.__dict__["_dont_enforce_csrf_checks"] = True
        response = verify(request)
        assert isinstance(response, HttpResponse)
        return response

    def middleware_response(
        self, middleware: BotProtectionMiddleware, request: HttpRequest
    ) -> HttpResponse:
        response = middleware(request)
        assert isinstance(response, HttpResponse)
        return response

    def challenge_response(self, request: HttpRequest) -> HttpResponse:
        response = challenge_page(request)
        assert isinstance(response, HttpResponse)
        return response

    def test_solution_cookie_replay(self) -> None:
        payload = self.solution(self.request())
        response = self.redeem(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["redirect"], "/?a=1&b=2")
        cookie = response.cookies["weblate_pow"]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        request = self.request()
        request.COOKIES["weblate_pow"] = cookie.value
        self.assertTrue(clearance(request))
        request.META["REMOTE_ADDR"] = "192.0.2.1"
        self.assertFalse(clearance(request))
        self.assertEqual(self.redeem(payload).status_code, 409)

    def test_invalid(self) -> None:
        invalid_payloads: tuple[object, ...] = (
            {},
            [],
            {"challenge": []},
            {"solution": 0},
        )
        for value in invalid_payloads:
            self.assertEqual(self.redeem(value).status_code, 400)
        payload = self.solution(self.request())
        payload["solution"]["counter"] = -1
        self.assertEqual(self.redeem(payload).status_code, 400)
        payload["challenge"]["parameters"]["cost"] = 1000000
        self.assertEqual(self.redeem(payload).status_code, 400)
        self.assertEqual(self.redeem("x" * 9000).status_code, 400)

    def test_boolean_pow_parameters_are_rejected_before_hashing(self) -> None:
        for field in ("cost", "expiresAt", "counter"):
            for value in (False, True):
                with self.subTest(field=field, value=value):
                    payload = self.solution(self.request())
                    parameters = (
                        payload["solution"]
                        if field == "counter"
                        else payload["challenge"]["parameters"]
                    )
                    parameters[field] = value
                    with patch(
                        "weblate.utils.bot_protection.verify_solution",
                        side_effect=AssertionError,
                    ):
                        self.assertEqual(self.redeem(payload).status_code, 400)

    def middleware(self) -> BotProtectionMiddleware:
        with patch(
            "weblate.utils.bot_protection.settings.CACHES",
            {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
        ):
            return BotProtectionMiddleware(lambda _request: HttpResponse("allowed"))

    def test_replay_cache_backends(self) -> None:
        for backend in (
            "django.core.cache.backends.locmem.LocMemCache",
            "django.core.cache.backends.dummy.DummyCache",
            "django.core.cache.backends.filebased.FileBasedCache",
            "django.core.cache.backends.db.DatabaseCache",
        ):
            with (
                self.subTest(backend=backend),
                override_settings(CACHES={"default": {"BACKEND": backend}}),
                self.assertRaisesMessage(
                    ImproperlyConfigured, "shared Redis or Memcached"
                ),
            ):
                BotProtectionMiddleware(lambda _request: HttpResponse())
        for backend in (
            "django.core.cache.backends.redis.RedisCache",
            "django_redis.cache.RedisCache",
            "django.core.cache.backends.memcached.PyMemcacheCache",
            "django.core.cache.backends.memcached.PyLibMCCache",
        ):
            with (
                self.subTest(backend=backend),
                override_settings(CACHES={"default": {"BACKEND": backend}}),
            ):
                BotProtectionMiddleware(lambda _request: HttpResponse())

    def test_challenge_deadlines(self) -> None:
        for age in (10, 300, 1800, 3600):
            with (
                self.subTest(age=age),
                override_settings(BOT_PROTECTION_CHALLENGE_AGE=age),
                patch(
                    "weblate.utils.bot_protection.time", time=Mock(return_value=1000)
                ),
            ):
                response = self.challenge_response(self.request())
                self.assertEqual(
                    int(response.cookies["weblate_pow_csrf"]["max-age"]), age
                )
                match = re.search(r'data-timeout="([0-9]+)"', response.text)
                assert match is not None
                self.assertEqual(int(match[1]), age * 1000)
                self.assertIn('aria-atomic="true"', response.text)

    def test_browser_and_methods(self) -> None:
        middleware = self.middleware()
        request = self.request("/?x=1")
        response = self.middleware_response(middleware, request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"pow-challenge", response.content)
        self.assertIn("weblate_pow_csrf", response.cookies)
        for method in ("HEAD", "POST", "OPTIONS"):
            request = self.request()
            request.method = method
            response = self.middleware_response(middleware, request)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(b"<html", response.content)

    def test_exemptions_and_auth(self) -> None:
        middleware = self.middleware()
        for exempt_path in (
            "/healthz/",
            "/accounts/login/",
            "/hooks/github/",
            "/static/a.js",
        ):
            self.assertEqual(
                self.middleware_response(
                    middleware, self.request(exempt_path)
                ).status_code,
                200,
            )
        request = self.factory.get("/api/projects/", HTTP_ACCEPT="application/json")
        self.assertEqual(self.middleware_response(middleware, request).status_code, 200)
        request = self.request()
        request.COOKIES["sessionid"] = "session"
        with patch(
            "weblate.utils.bot_protection.auth.get_user",
            return_value=Mock(is_authenticated=True),
        ):
            self.assertEqual(
                self.middleware_response(middleware, request).status_code, 200
            )

    @override_settings(
        BOT_PROTECTION_EXEMPT_AGENTS=[r"^Weblate-Uptime/1\.0$", r"TrustedMonitor"],
        BOT_PROTECTION_UNWANTED_AGENTS=["uptime", "monitor"],
        BOT_PROTECTION_UNWANTED_ACTION="deny",
    )
    def test_exempt_agents(self) -> None:
        for deployment_prefix in ("", "/hosted"):
            with override_settings(URL_PREFIX=deployment_prefix):
                middleware = self.middleware()
                with (
                    patch(
                        "weblate.utils.bot_protection.auth.get_user",
                        side_effect=AssertionError,
                    ),
                    patch(
                        "weblate.utils.bot_protection.clearance",
                        side_effect=AssertionError,
                    ),
                    patch.object(
                        middleware.crawlers, "verified", side_effect=AssertionError
                    ),
                ):
                    for agent in ("weblate-UPTIME/1.0", "check (TrustedMonitor/2.0)"):
                        for method in ("GET", "HEAD", "POST"):
                            for route in ("/", "/search/"):
                                with self.subTest(
                                    prefix=deployment_prefix,
                                    agent=agent,
                                    method=method,
                                    route=route,
                                ):
                                    request = self.factory.generic(
                                        method,
                                        deployment_prefix + route,
                                        HTTP_USER_AGENT=agent,
                                    )
                                    request.COOKIES["sessionid"] = "session"
                                    self.assertEqual(
                                        self.middleware_response(
                                            middleware, request
                                        ).status_code,
                                        200,
                                    )

    @override_settings(
        BOT_PROTECTION_EXEMPT_AGENTS=[r"^Weblate-Uptime/1\.0$", "TrustedMonitor"]
    )
    def test_nonmatching_agents(self) -> None:
        middleware = self.middleware()
        for agent in (
            "",
            "Browser",
            "Weblate-Uptime/1x0",
            "Weblate-Uptime/1.0 extra",
            "x" * 1024 + "TrustedMonitor",
        ):
            with self.subTest(agent=agent):
                self.assertEqual(
                    self.middleware_response(
                        middleware, self.request(HTTP_USER_AGENT=agent)
                    ).status_code,
                    403,
                )
        self.assertEqual(
            self.middleware_response(middleware, self.request()).status_code, 403
        )
        with override_settings(BOT_PROTECTION_EXEMPT_AGENTS=[]):
            self.assertEqual(
                self.middleware_response(
                    self.middleware(), self.request(HTTP_USER_AGENT="TrustedMonitor")
                ).status_code,
                403,
            )

    def test_invalid_exempt_agent(self) -> None:
        with (
            override_settings(BOT_PROTECTION_EXEMPT_AGENTS=["["]),
            self.assertRaisesMessage(
                ImproperlyConfigured, "BOT_PROTECTION_EXEMPT_AGENTS"
            ),
        ):
            self.middleware()
        with override_settings(
            BOT_PROTECTION_ENABLED=False, BOT_PROTECTION_EXEMPT_AGENTS=["["]
        ):
            self.assertEqual(
                self.middleware_response(self.middleware(), self.request()).status_code,
                200,
            )

    @override_settings(BOT_PROTECTION_EXEMPT_AGENTS=["TrustedMonitor"])
    def test_exempt_agent_cannot_bypass_verification(self) -> None:
        middleware = self.middleware()
        request = self.request("/-/pow/verify/", HTTP_USER_AGENT="TrustedMonitor")
        response = self.middleware_response(middleware, request)
        self.assertEqual(response.status_code, 405)
        request = self.factory.post(
            "/-/pow/verify/",
            "{}",
            content_type="application/json",
            HTTP_USER_AGENT="TrustedMonitor",
        )
        request.__dict__["_dont_enforce_csrf_checks"] = True
        response = self.middleware_response(middleware, request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["error"], "invalid_solution")

    def test_authentication_assets_and_git_protocol_exemptions(self) -> None:
        for deployment_prefix in ("", "/hosted"):
            with override_settings(URL_PREFIX=deployment_prefix):
                middleware = self.middleware()
                for route, method in (
                    ("/js/i18n/", "GET"),
                    ("/git/project/component/info/refs?service=git-upload-pack", "GET"),
                    ("/git/project/component/git-upload-pack", "POST"),
                    ("/git/project/component/git-receive-pack", "POST"),
                    ("/git/project/component.git/info/refs", "GET"),
                    ("/projects/project/component.git/info/refs", "GET"),
                    ("/projects/project/component/info/refs", "GET"),
                ):
                    with self.subTest(
                        prefix=deployment_prefix, route=route, method=method
                    ):
                        request = self.factory.generic(
                            method, deployment_prefix + route
                        )
                        if deployment_prefix:
                            request.__dict__["urlconf"] = (
                                path("hosted/", include(real_patterns)),
                            )
                        with patch.object(
                            middleware, "classify", side_effect=AssertionError
                        ):
                            self.assertEqual(
                                self.middleware_response(
                                    middleware, request
                                ).status_code,
                                200,
                            )
                for route in (
                    "/js/i18n/extra/",
                    "/js/component-branches/",
                    "/git-other/project/info/refs",
                    "/git/project/component/",
                    "/projects/project/component/",
                    "/projects/project/info/refs/",
                ):
                    self.assertEqual(
                        self.middleware_response(
                            middleware, self.request(deployment_prefix + route)
                        ).status_code,
                        403,
                    )

    def test_changes_rss_routes_are_exempt(self) -> None:
        for deployment_prefix in ("", "/hosted"):
            with override_settings(URL_PREFIX=deployment_prefix):
                middleware = self.middleware()
                for route in ("/changes/rss/", "/changes/rss/project/component/cs/"):
                    for method in ("GET", "HEAD"):
                        with self.subTest(
                            prefix=deployment_prefix, route=route, method=method
                        ):
                            request = self.factory.generic(
                                method,
                                deployment_prefix + route,
                                HTTP_ACCEPT="application/rss+xml",
                            )
                            with patch.object(
                                middleware, "classify", side_effect=AssertionError
                            ):
                                self.assertEqual(
                                    self.middleware_response(
                                        middleware, request
                                    ).status_code,
                                    200,
                                )
                for route in ("/changes/", "/changes/rss-other/", "/changes/rss"):
                    self.assertEqual(
                        self.middleware_response(
                            middleware, self.request(deployment_prefix + route)
                        ).status_code,
                        403,
                    )

    @override_settings(
        LANGUAGES=(
            ("en", "English"),
            ("cs", "Czech"),
            ("pt-br", "Portuguese"),
            ("ba", "Bashkir"),  # codespell:ignore
        ),
        LANGUAGE_CODE="en",
    )
    def test_rendered_challenge_language(self) -> None:
        for accept, expected in (
            ("en", "en"),
            ("cs", "cs"),
            ("pt-BR", "pt-br"),
            ("ba", "ba"),  # codespell:ignore
            ("unknown", "en"),
            ("<invalid>", "en"),
        ):
            with self.subTest(accept=accept):
                response = self.challenge_response(
                    self.request(HTTP_ACCEPT_LANGUAGE=accept)
                )
                self.assertIn(f'<html lang="{expected}" dir="ltr">', response.text)
                self.assertNotIn("{{ language }}", response.text)

    def test_feature_tips(self) -> None:
        self.assertEqual(len(FEATURE_TIPS), 20)
        self.assertEqual(len(set(FEATURE_TIPS)), 20)
        for tip in FEATURE_TIPS:
            with (
                self.subTest(tip=tip),
                patch("weblate.utils.bot_protection.random.choice", return_value=tip),
            ):
                response = self.challenge_response(self.request())
                self.assertContains(response, tip, status_code=403)
                self.assertEqual(response.text.count('id="pow-tip"'), 1)

    @override_settings(LANGUAGES=(("ar", "Arabic"),), LANGUAGE_CODE="ar")
    def test_challenge_rtl(self) -> None:
        response = self.challenge_response(self.request(HTTP_ACCEPT_LANGUAGE="ar"))
        self.assertContains(response, '<html lang="ar" dir="rtl">', status_code=403)
        self.assertContains(response, "bootstrap5_rtl.css", status_code=403)

    def test_feature_tip_translation(self) -> None:
        def translate_tip(message: str) -> str:
            self.assertIn(message, FEATURE_TIPS)
            self.assertEqual(get_language(), "cs")
            return "Translated feature tip"

        with patch("weblate.utils.bot_protection.gettext", side_effect=translate_tip):
            response = self.challenge_response(self.request(HTTP_ACCEPT_LANGUAGE="cs"))
        self.assertContains(response, "Translated feature tip", status_code=403)

    def test_oidc_protocol_routes_are_exempt(self) -> None:
        # Use the provider URLconf so added endpoints receive coverage as well.
        for deployment_prefix in ("", "/hosted"):
            with override_settings(URL_PREFIX=deployment_prefix):
                middleware = self.middleware()
                for pattern in oidc_patterns:
                    route = (
                        deployment_prefix
                        + "/oidc"
                        + reverse(pattern.name, urlconf="weblate.oidc.urls")
                    )
                    for method in ("GET", "HEAD", "POST", "OPTIONS"):
                        with self.subTest(route=route, method=method):
                            request = self.request(route)
                            request.method = method
                            with patch.object(
                                middleware, "classify", side_effect=AssertionError
                            ):
                                self.assertEqual(
                                    self.middleware_response(
                                        middleware, request
                                    ).status_code,
                                    200,
                                )
                # Neither the removed SAML prefix nor similar names bypass PoW.
                for route in ("/idp/", "/oidc-other/", "/oidc"):
                    self.assertEqual(
                        self.middleware_response(
                            middleware, self.request(deployment_prefix + route)
                        ).status_code,
                        403,
                    )

    def test_clearance_endpoint(self) -> None:
        request = self.request("/-/pow/check/")
        self.assertEqual(check_clearance(request).status_code, 403)
        response = self.redeem(self.solution(self.request()))
        request.COOKIES["weblate_pow"] = response.cookies["weblate_pow"].value
        for method in ("GET", "HEAD"):
            request.method = method
            with patch(
                "weblate.utils.bot_protection.caches", side_effect=AssertionError
            ):
                result = check_clearance(request)
            self.assertEqual(result.status_code, 204)
            self.assertEqual(result.content, b"")
            self.assertEqual(result["Cache-Control"], "private, no-store")
        request.method = "POST"
        self.assertEqual(check_clearance(request).status_code, 405)
        request.method = "GET"
        request.COOKIES["weblate_pow"] += "x"
        self.assertEqual(check_clearance(request).status_code, 403)
        with override_settings(BOT_PROTECTION_ENABLED=False):
            self.assertEqual(check_clearance(request).status_code, 404)

    def test_clearance_middleware_and_destination_permissions(self) -> None:
        for deployment_prefix in ("", "/hosted"):
            with override_settings(URL_PREFIX=deployment_prefix):
                middleware = self.middleware()
                downstream = Mock(
                    return_value=HttpResponse("Application denial", status=403)
                )
                middleware.get_response = downstream
                check = self.request(deployment_prefix + "/-/pow/check/")
                with patch.object(middleware, "classify", side_effect=AssertionError):
                    self.assertEqual(
                        self.middleware_response(middleware, check).status_code, 403
                    )
                downstream.assert_not_called()
                # Issue a cookie bound to this deployment.
                with patch(
                    "weblate.utils.bot_protection.safe_target", return_value=True
                ):
                    response = self.redeem(self.solution(self.request()))
                check.COOKIES["weblate_pow"] = response.cookies["weblate_pow"].value
                self.assertEqual(
                    self.middleware_response(middleware, check).status_code, 204
                )
                downstream.assert_not_called()
                destination = self.request(deployment_prefix + "/projects/")
                destination.COOKIES.update(check.COOKIES)
                result = self.middleware_response(middleware, destination)
                self.assertEqual(result.content, b"Application denial")
                downstream.assert_called_once()

    def test_disabled_crawlers_do_not_load(self) -> None:
        with (
            override_settings(BOT_PROTECTION_ENABLED=False),
            patch("pathlib.Path.open", side_effect=AssertionError),
        ):
            self.middleware()

    def test_verification_counters(self) -> None:
        with patch(
            "weblate.utils.bot_protection.time", time=Mock(return_value=1800000000)
        ):
            with self.assertLogs("weblate.bot_protection", level="INFO") as logs:
                record_outcome("success", 200)
                record_outcome("success", 200)
                record_outcome("expired_challenge", 400)
            self.assertEqual(vars(logs.records[0])["reason"], "success")
            self.assertEqual(vars(logs.records[0])["count"], 1)
            stats = verification_stats()
            assert stats is not None
            self.assertEqual(stats["success"], 2)
            self.assertEqual(stats["expired_challenge"], 1)
        with patch(
            "weblate.utils.bot_protection.time",
            time=Mock(return_value=1800000000 + 86400),
        ):
            stats = verification_stats()
            assert stats is not None
            self.assertEqual(stats["success"], 0)
        with patch(
            "django.core.cache.backends.locmem.LocMemCache.get_many",
            side_effect=ConnectionError,
        ):
            self.assertIsNone(verification_stats())

    def test_outcome_recorded_once_per_response(self) -> None:
        payload = self.solution(self.request())
        with patch("weblate.utils.bot_protection.record_outcome") as record:
            self.assertEqual(self.redeem(payload).status_code, 200)
            record.assert_called_once_with("success", 200)
            record.reset_mock()
            self.assertEqual(self.redeem(payload).status_code, 409)
            record.assert_called_once_with("replayed_challenge", 409)
            record.reset_mock()
            self.assertEqual(self.redeem({}).status_code, 400)
            record.assert_called_once_with("invalid_solution", 400)
            record.reset_mock()
            request = self.factory.post(
                "/-/pow/verify/", "{}", content_type="application/json"
            )
            self.assertEqual(verify(request).status_code, 403)
            record.assert_called_once_with("csrf_failed", 403)
            record.reset_mock()
            with patch(
                "weblate.utils.bot_protection.time",
                time=Mock(return_value=time.time() + 1000),
            ):
                self.assertEqual(self.redeem(payload).status_code, 400)
            record.assert_called_once_with("expired_challenge", 400)
            record.reset_mock()
            with patch(
                "django.core.cache.backends.locmem.LocMemCache.add",
                side_effect=ConnectionError,
            ):
                self.assertEqual(
                    self.redeem(self.solution(self.request())).status_code, 503
                )
            record.assert_called_once_with("verification_unavailable", 503)

    def test_expired_error(self) -> None:
        payload = self.solution(self.request())
        with patch(
            "weblate.utils.bot_protection.time",
            time=Mock(return_value=time.time() + 1000),
        ):
            response = self.redeem(payload)
        self.assertEqual(json.loads(response.content)["error"], "expired_challenge")

    def test_csrf(self) -> None:
        request = self.factory.post(
            "/-/pow/verify/", "{}", content_type="application/json"
        )
        self.assertEqual(verify(request).status_code, 403)

    def test_no_kdf_generation(self) -> None:
        with patch(
            "altcha.v2._select_derive_key",
            return_value=Mock(side_effect=AssertionError),
        ):
            self.assertEqual(challenge_page(self.request()).status_code, 403)

    def test_expiry_forgery_and_cookie_tampering(self) -> None:
        payload = self.solution(self.request())
        payload["challenge"]["signature"] = "0" * 64
        self.assertEqual(self.redeem(payload).status_code, 400)
        payload = self.solution(self.request())
        with patch(
            "weblate.utils.bot_protection.time",
            time=Mock(return_value=time.time() + 1000),
        ):
            self.assertEqual(self.redeem(payload).status_code, 400)
        response = self.redeem(self.solution(self.request()))
        request = self.request()
        request.COOKIES["weblate_pow"] = response.cookies["weblate_pow"].value
        with patch(
            "django.core.signing.time", time=Mock(return_value=time.time() + 4000)
        ):
            self.assertFalse(clearance(request))
        request.COOKIES["weblate_pow"] += "x"
        self.assertFalse(clearance(request))

    def test_session_expiration_and_anubis(self) -> None:
        middleware = self.middleware()
        request = self.request()
        request.COOKIES.update(
            {"sessionid": "expired", "techaro.lol-anubis-auth": "untrusted"}
        )
        with patch(
            "weblate.utils.bot_protection.auth.get_user",
            return_value=Mock(is_authenticated=False),
        ):
            self.assertEqual(
                self.middleware_response(middleware, request).status_code, 403
            )
        request.COOKIES.clear()
        self.assertEqual(self.middleware_response(middleware, request).status_code, 403)

    def test_crawlers(self) -> None:
        middleware = self.middleware()
        middleware.crawlers.ranges = {"googlebot": [ip_network("192.0.2.0/24")]}
        request = self.request(
            HTTP_USER_AGENT="Googlebot (+http://www.google.com/bot.html)"
        )
        self.assertEqual(self.middleware_response(middleware, request).status_code, 403)
        request.META["REMOTE_ADDR"] = "192.0.2.7"
        self.assertEqual(self.middleware_response(middleware, request).status_code, 200)
        request = self.request(HTTP_USER_AGENT="browser", REMOTE_ADDR="192.0.2.7")
        self.assertEqual(self.middleware_response(middleware, request).status_code, 403)

    def test_crawler_crawl_policy(self) -> None:
        middleware = self.middleware()
        with patch.object(middleware.crawlers, "verified", return_value=True):
            for route in (
                "/",
                "/projects/",
                "/engage/test/",
                "/sitemap.xml",
                "/sitemap-project.xml",
            ):
                for method in ("GET", "HEAD"):
                    request = self.factory.generic(method, route)
                    self.assertEqual(middleware.classify(request), "allow")
            for route in (
                "/search/",
                "/translate/project/component/en/",
                "/projects-other/",
                "/sitemap.xml/extra",
            ):
                self.assertEqual(middleware.classify(self.request(route)), "challenge")
            request = self.factory.post("/projects/")
            self.assertEqual(middleware.classify(request), "challenge")
            with override_settings(
                BOT_PROTECTION_UNWANTED_AGENTS=["Googlebot"],
                BOT_PROTECTION_UNWANTED_ACTION="deny",
            ):
                self.assertEqual(
                    middleware.classify(
                        self.request("/search/", HTTP_USER_AGENT="Googlebot")
                    ),
                    "deny",
                )
                self.assertEqual(
                    middleware.classify(
                        self.request("/projects/", HTTP_USER_AGENT="Googlebot")
                    ),
                    "allow",
                )

    def test_prefixed_crawler_policy(self) -> None:
        with override_settings(URL_PREFIX="/hosted"):
            middleware = self.middleware()
            with patch.object(middleware.crawlers, "verified", return_value=True):
                self.assertEqual(
                    middleware.classify(self.request("/hosted/projects/?page=2")),
                    "allow",
                )
                self.assertEqual(
                    middleware.classify(self.request("/hosted/search/")), "challenge"
                )
                self.assertEqual(
                    middleware.classify(self.request("/hosted-other/projects/")),
                    "challenge",
                )

    def test_legacy_widgets(self) -> None:
        for deployment_prefix in ("", "/hosted"):
            urlconf = (
                (path(deployment_prefix.strip("/") + "/", include(real_patterns)),)
                if deployment_prefix
                else tuple(real_patterns)
            )
            with override_settings(URL_PREFIX=deployment_prefix, ROOT_URLCONF=urlconf):
                middleware = self.middleware()
                for route, expected in (
                    ("/widgets/project/-/svg-badge.svg", 200),
                    ("/widgets/project/en/svg-badge.svg", 200),
                    ("/widgets/project/-/component/svg-badge.svg", 200),
                    ("/widgets/project/en/component/svg-badge.svg", 200),
                    ("/widget/project/svg-badge.svg", 200),
                    ("/widgets/project/", 403),
                    ("/widgets/", 403),
                    ("/widgets-other/project/", 403),
                ):
                    with self.subTest(prefix=deployment_prefix, route=route):
                        request = self.request(deployment_prefix + route)
                        self.assertEqual(
                            self.middleware_response(middleware, request).status_code,
                            expected,
                        )
                        if expected == 200 and route.startswith("/widgets/"):
                            match = resolve(request.path_info)
                            response = match.func(request, **match.kwargs)
                            self.assertEqual(response.status_code, 301)
                            self.assertTrue(
                                response["Location"].startswith(
                                    deployment_prefix + "/widget/"
                                )
                            )

    def test_account_flows_bypass_classification(self) -> None:
        middleware = self.middleware()
        with patch.object(middleware, "classify", side_effect=AssertionError):
            for route in (
                "login/",
                "register/",
                "reset/",
                "confirm/",
                "complete/email/",
                "login/saml/",
                "auth/second-factor/totp/",
                "auth/webauthn/authentication/begin/",
                "auth/webauthn/authentication/complete/",
                "auth/webauthn/jsi18n/",
                "unsubscribe/?i=invalid",
            ):
                for method in ("GET", "POST"):
                    request = self.factory.generic(method, "/accounts/" + route)
                    self.assertEqual(
                        self.middleware_response(middleware, request).status_code, 200
                    )

    def test_public_asset_exemptions(self) -> None:
        middleware = self.middleware()
        for route in (
            "/css/custom.css",
            "/site.webmanifest",
            "/browserconfig.xml",
            "/apple-touch-icon.png",
            "/favicon-192x192.png",
            "/android-chrome-512x512.png",
            "/exports/og.png",
            "/security.txt",
        ):
            self.assertEqual(
                self.middleware_response(middleware, self.request(route)).status_code,
                200,
            )
        for route in (
            "/css/other.css",
            "/exports/other.png",
            "/favicon-192x192.png/extra",
        ):
            self.assertEqual(
                self.middleware_response(middleware, self.request(route)).status_code,
                403,
            )

    def test_csrf_success(self) -> None:
        request = self.request()
        page = challenge_page(request)
        payload = self.solution(request)
        post = self.factory.post(
            "/-/pow/verify/",
            json.dumps(payload),
            content_type="application/json",
            HTTP_ORIGIN="https://testserver",
            secure=True,
        )
        post.COOKIES["weblate_pow_csrf"] = page.cookies["weblate_pow_csrf"].value
        post.META["HTTP_X_CSRFTOKEN"] = request.META["CSRF_COOKIE"]
        self.assertEqual(verify(post).status_code, 200)
        post = self.factory.post(
            "/-/pow/verify/",
            "{}",
            content_type="application/json",
            HTTP_ORIGIN="https://evil.example",
            secure=True,
        )
        self.assertEqual(verify(post).status_code, 403)

    def test_verification_hash_count(self) -> None:
        payload = self.solution(self.request())
        with patch("altcha.v2.derive_key_sha", wraps=derive_key_sha) as derive:
            self.assertEqual(self.redeem(payload).status_code, 200)
            self.assertEqual(derive.call_count, 1)

    def test_cache_failure_and_simultaneous_redemption(self) -> None:
        payload = self.solution(self.request())
        with patch(
            "django.core.cache.backends.locmem.LocMemCache.add",
            side_effect=ConnectionError,
        ):
            self.assertEqual(self.redeem(payload).status_code, 503)
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(
                pool.map(lambda _index: self.redeem(payload).status_code, range(8))
            )
        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(409), 7)
        stats = verification_stats()
        assert stats is not None
        self.assertEqual(stats["success"], 1)
        self.assertEqual(stats["replayed_challenge"], 7)

    def test_prefix_and_unsafe_targets(self) -> None:
        with override_settings(URL_PREFIX="/hosted"):
            self.assertTrue(safe_target("/hosted/projects/?q=x"))
            for value in (
                "//evil.example/",
                "https://evil.example/",
                "/projects/",
                "/hosted/\\evil",
                "/hosted/\n",
            ):
                self.assertFalse(safe_target(value))
            self.assertEqual(
                self.middleware_response(
                    self.middleware(), self.request("/hosted/accounts/login/")
                ).status_code,
                200,
            )

    def test_difficulty_and_disabled(self) -> None:
        for value in (-1, 0, 7, True, "4"):
            with (
                override_settings(BOT_PROTECTION_DIFFICULTY=value),
                self.assertRaises(ImproperlyConfigured),
            ):
                self.middleware()
        with override_settings(BOT_PROTECTION_ENABLED=False):
            self.assertEqual(
                self.middleware_response(self.middleware(), self.request()).status_code,
                200,
            )

    async def test_async(self) -> None:
        async def response(_request: HttpRequest) -> HttpResponse:  # ruff: ignore[unused-async]
            return HttpResponse("allowed")

        with patch(
            "weblate.utils.bot_protection.settings.CACHES",
            {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
        ):
            middleware = BotProtectionMiddleware(response)
        pending = middleware(self.request())
        assert isawaitable(pending)
        result = await pending
        self.assertEqual(result.status_code, 403)

    @skipUnless(
        shutil.which("node"), "Node.js is needed to exercise browser challenge handling"
    )
    def test_browser_deadline_and_failure_announcement(self) -> None:
        script = """
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('weblate/static/js/bot-challenge.js', 'utf8');
(async () => {
  for (const timeout of [10000, 300000, 1800000, 3600000]) {
    for (const failure of ['worker', 'verification', 'timeout']) {
      let worker, deadline, cleared = false;
      const status = {textContent: 'Working', hidden: false};
      const message = 'Verification failed. Retry or sign in.';
      const elements = {
        'pow-form': {dataset: {worker: '/worker.js', url: '/verify/', timeout: String(timeout)},
                     querySelector: () => ({value: 'csrf'})},
        'pow-error': {textContent: message, hidden: true},
        'pow-status': status,
        'pow-retry': {addEventListener: () => {}},
        'pow-challenge': {textContent: '{"parameters":{}}'},
      };
      vm.runInNewContext(code, {
        document: {getElementById: id => elements[id]},
        Worker: class {
          constructor() {worker = this; this.terminated = false;}
          postMessage() {}
          terminate() {this.terminated = true;}
        },
        setTimeout: (callback, delay) => {deadline = {callback, delay}; return 1;},
        clearTimeout: () => {cleared = true;},
        fetch: async () => ({ok: false, json: async () => ({error: "unknown"})}),
      });
      assert.equal(deadline.delay, timeout);
      if (failure === 'worker') worker.onerror();
      if (failure === 'timeout') deadline.callback();
      if (failure === 'verification') await worker.onmessage({data: {solution: {}}});
      assert.equal(status.hidden, false);
      assert.equal(status.textContent, message);
      assert.equal(worker.terminated, true);
      assert.equal(cleared, true);
    }
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        node = shutil.which("node")
        assert node is not None
        subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

    @skipUnless(shutil.which("node"), "Node.js is needed for browser tests")
    def test_browser_recovery_and_clearance(self) -> None:
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('weblate/static/js/bot-challenge.js', 'utf8');
(async () => {
  for (const scenario of ['success', 'invalid_solution', 'replayed_challenge',
      'csrf_failed', 'verification_unavailable', 'expired_challenge',
      'clearance', 'network', 'worker', 'constructor', 'malformed']) {
    let worker, retry, deadline, navigated, reloads = 0;
    const calls = [], storage = new Map();
    const elements = {
      'pow-form': {dataset: {worker: '/worker.js', url: '/verify/', check: '/check/', timeout: '10000'},
        querySelector: () => ({value: 'csrf'})},
      'pow-status': {textContent: 'working'}, 'pow-error': {textContent: 'error'},
      'pow-retry': {addEventListener: (_, callback) => {retry = callback;}},
      'pow-challenge': {textContent: '{}'},
    };
    for (const reason of ['expired', 'invalid', 'replayed', 'csrf', 'unavailable', 'clearance']) {
      elements[`pow-${reason}`] = {textContent: reason};
    }
    vm.runInNewContext(code, {
      document: {getElementById: id => elements[id]},
      sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
        removeItem: key => storage.delete(key)},
      location: {reload: () => {reloads++;}, replace: url => {navigated = url;}},
      Worker: class {
        constructor() {if (scenario === 'constructor') throw Error(); worker = this;}
        postMessage() {}
        terminate() {}
      },
      setTimeout: callback => {deadline = callback; return 1;}, clearTimeout: () => {},
      fetch: async (url, options) => {
        calls.push([url, options.method]);
        if (scenario === 'network') throw Error();
        if (url === '/check/') return {status: scenario === 'clearance' ? 403 : 204};
        const status = {invalid_solution: 400, replayed_challenge: 409, csrf_failed: 403,
          verification_unavailable: 503, expired_challenge: 400}[scenario] || 200;
        return {ok: status === 200, status, json: async () => {
          if (scenario === 'malformed') throw Error();
          return status === 200 ? {redirect: '/destination/'} : {error: scenario};
        }};
      },
    });
    if (scenario === 'worker') worker.onerror();
    else if (scenario !== 'constructor') await worker.onmessage({data: {solution: {}}});
    if (scenario === 'success') {
      assert.deepEqual(calls, [['/verify/', 'POST'], ['/check/', 'HEAD']]);
      assert.equal(navigated, '/destination/');
    } else {
      assert.equal(navigated, undefined);
      const expected = {invalid_solution: 'invalid', replayed_challenge: 'replayed',
        csrf_failed: 'csrf', verification_unavailable: 'unavailable',
        expired_challenge: 'expired', clearance: 'clearance', constructor: 'error'}[scenario] || 'error';
      assert.equal(elements['pow-status'].textContent, expected);
      if (scenario === 'expired_challenge') {
        assert.equal(reloads, 1);
        deadline();
        assert.equal(reloads, 1);
      }
      retry();
      assert.equal(storage.size, 0);
      assert.ok(reloads > 0);
    }
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        node = shutil.which("node")
        assert node is not None
        subprocess.run(
            [node, "-e", script], check=True, capture_output=True, text=True, timeout=30
        )

    @skipUnless(
        shutil.which("node"), "Node.js is needed to exercise the browser worker"
    )
    def test_browser_worker_protocol(self) -> None:
        payload = self.solution(self.request())
        script = """
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto').webcrypto;
const self = { postMessage: data => {
  if (data.solution) process.stdout.write(JSON.stringify(data));
}};
vm.runInNewContext(fs.readFileSync('weblate/static/js/bot-worker.js', 'utf8'),
                   {self, crypto, Uint8Array, DataView});
self.onmessage({data: JSON.parse(fs.readFileSync(0, 'utf8'))});
"""
        node = shutil.which("node")
        assert node is not None
        result = subprocess.run(
            [node, "-e", script],
            input=json.dumps(payload["challenge"]),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        self.assertEqual(self.redeem(json.loads(result.stdout)).status_code, 200)


urlpatterns = [path("", lambda _request: HttpResponse("allowed"))]


@override_settings(
    ROOT_URLCONF=__name__,
    BOT_PROTECTION_ENABLED=True,
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    BOT_PROTECTION_CACHE_ALIAS="pow",
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "pow": {"BACKEND": "django.core.cache.backends.redis.RedisCache"},
    },
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "weblate.utils.bot_protection.BotProtectionMiddleware",
        "weblate.accounts.middleware.AuthenticationMiddleware",
    ],
)
class SessionProofTest(TestCase):
    def test_login_logout_and_expiration(self) -> None:
        user = User.objects.create_user(
            username="pow-session-user", password="testpass"
        )
        self.assertEqual(
            self.client.get("/", headers={"accept": "text/html"}).status_code, 403
        )
        self.client.force_login(user)
        self.assertEqual(
            self.client.get("/", headers={"accept": "text/html"}).status_code, 200
        )
        self.assertNotIn("weblate_pow", self.client.cookies)
        self.client.logout()
        self.assertEqual(
            self.client.get("/", headers={"accept": "text/html"}).status_code, 403
        )
        self.client.force_login(user)
        self.client.cookies["sessionid"] = "invalid-session"
        self.assertEqual(
            self.client.get("/", headers={"accept": "text/html"}).status_code, 403
        )

    @override_settings(
        ROOT_URLCONF="weblate.urls",
        BOT_PROTECTION_EXEMPT_AGENTS=["TrustedMonitor"],
        REQUIRE_LOGIN=True,
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "weblate.utils.bot_protection.BotProtectionMiddleware",
            "weblate.accounts.middleware.AuthenticationMiddleware",
            "django.contrib.auth.middleware.LoginRequiredMiddleware",
        ],
    )
    def test_exempt_agent_still_requires_login(self) -> None:
        response = self.client.get(
            "/projects/", headers={"user-agent": "TrustedMonitor"}
        )
        self.assertRedirects(
            response, "/accounts/login/?next=/projects/", fetch_redirect_response=False
        )
        self.assertNotIn("weblate_pow", self.client.cookies)

    @override_settings(
        ROOT_URLCONF="weblate.urls",
        REQUIRE_LOGIN=True,
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "weblate.utils.bot_protection.BotProtectionMiddleware",
            "weblate.accounts.middleware.AuthenticationMiddleware",
            "django.contrib.auth.middleware.LoginRequiredMiddleware",
        ],
    )
    def test_account_redirects_and_public_assets(self) -> None:
        for route in (
            "/accounts/profile/",
            "/accounts/userdata/",
            "/accounts/password/",
        ):
            self.assertRedirects(
                self.client.get(route),
                "/accounts/login/?next=" + route,
                fetch_redirect_response=False,
            )
        for route in (
            "/accounts/login/",
            "/css/custom.css",
            "/site.webmanifest",
            "/browserconfig.xml",
            "/robots.txt",
        ):
            self.assertEqual(self.client.get(route).status_code, 200, route)
        response = self.client.get("/accounts/unsubscribe/?i=invalid")
        self.assertEqual(response.status_code, 302)
        user = User.objects.create_user(
            username="pow-settings-user", password="testpass"
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 200)
        self.assertNotIn("weblate_pow", self.client.cookies)
