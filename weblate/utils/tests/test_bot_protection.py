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
from django.urls import include, path, reverse
from django.utils.translation import get_language

from weblate.auth.models import User
from weblate.oidc.urls import urlpatterns as oidc_patterns
from weblate.urls import real_patterns
from weblate.utils.bot_protection import (
    FEATURE_TIPS,
    BotProtectionMiddleware,
    binding,
    challenge_page,
    clearance,
    safe_target,
    secret,
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
        middleware.crawlers.checked = time.monotonic()
        middleware.crawlers.ranges = {"googlebot": [ip_network("192.0.2.0/24")]}
        request = self.request(
            HTTP_USER_AGENT="Googlebot (+http://www.google.com/bot.html)"
        )
        self.assertEqual(self.middleware_response(middleware, request).status_code, 403)
        request.META["REMOTE_ADDR"] = "192.0.2.7"
        self.assertEqual(self.middleware_response(middleware, request).status_code, 200)
        request = self.request(HTTP_USER_AGENT="browser", REMOTE_ADDR="192.0.2.7")
        self.assertEqual(self.middleware_response(middleware, request).status_code, 403)

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
        fetch: async () => ({ok: false}),
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
