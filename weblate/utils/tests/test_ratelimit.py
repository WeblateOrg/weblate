# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from time import sleep

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage import default_storage
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.ratelimit import (
    RateLimitNotify,
    check_rate_limit,
    rate_limit_notify,
    reset_rate_limit,
    revert_rate_limit,
    session_ratelimit_post,
)


class RateLimitTest(SimpleTestCase):
    def get_request(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        request.method = "POST"
        request.session = SessionStore()
        request.user = AnonymousUser()

        # Initialize messages storage using fake middleware
        middleware = MessageMiddleware(lambda _request: HttpResponse())
        middleware.process_request(request)

        return request

    def setUp(self) -> None:
        # Ensure no rate limits are there, across combinations used in tests
        request = self.get_request()
        for attempts, window in [(5, 60), (1, 2), (2, 2), (1, 1)]:
            with override_settings(
                RATELIMIT_ATTEMPTS=attempts, RATELIMIT_WINDOW=window
            ):
                reset_rate_limit("test", request)

    def test_basic(self) -> None:
        self.assertTrue(check_rate_limit("test", self.get_request()))

    @override_settings(RATELIMIT_ATTEMPTS=5, RATELIMIT_WINDOW=60)
    def test_limit(self) -> None:
        request = self.get_request()
        for _unused in range(5):
            self.assertTrue(check_rate_limit("test", request))

        self.assertFalse(check_rate_limit("test", request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=2, RATELIMIT_LOCKOUT=1)
    def test_window(self) -> None:
        request = self.get_request()
        self.assertTrue(check_rate_limit("test", request))
        sleep(1)
        self.assertFalse(check_rate_limit("test", request))
        sleep(2)
        self.assertTrue(check_rate_limit("test", request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=2, RATELIMIT_LOCKOUT=100)
    def test_lockout(self) -> None:
        request = self.get_request()
        self.assertTrue(check_rate_limit("test", request))
        sleep(1)
        self.assertFalse(check_rate_limit("test", request))
        sleep(1)
        self.assertFalse(check_rate_limit("test", request))

    @override_settings(RATELIMIT_ATTEMPTS=2, RATELIMIT_WINDOW=2, RATELIMIT_LOCKOUT=100)
    def test_interval(self) -> None:
        request = self.get_request()
        self.assertTrue(check_rate_limit("test", request))
        sleep(1.5)
        self.assertTrue(check_rate_limit("test", request))
        sleep(1.5)
        self.assertTrue(check_rate_limit("test", request))
        sleep(1.5)
        self.assertTrue(check_rate_limit("test", request))

    @override_settings(RATELIMIT_ATTEMPTS=2, RATELIMIT_WINDOW=2)
    def test_revert(self) -> None:
        request = self.get_request()
        self.assertTrue(check_rate_limit("test", request))
        self.assertTrue(check_rate_limit("test", request))
        revert_rate_limit("test", request)
        self.assertTrue(check_rate_limit("test", request))
        self.assertFalse(check_rate_limit("test", request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=1, RATELIMIT_LOCKOUT=1)
    def test_post(self) -> None:
        request = self.get_request()

        limiter = session_ratelimit_post("test")(
            lambda request: "RESPONSE"  # noqa: ARG005
        )

        # First attempt should work
        self.assertEqual(limiter(request), "RESPONSE")
        # Second attempt should be blocked
        self.assertEqual(limiter(request).url, "/accounts/login/")
        # During lockout period request should be blocked
        request = self.get_request()
        self.assertEqual(limiter(request).url, "/accounts/login/")
        # Wait until lockout expires and it should work again
        sleep(1)
        request = self.get_request()
        self.assertEqual(limiter(request), "RESPONSE")


class RateLimitUserTest(RateLimitTest):
    def get_request(self):
        request = super().get_request()
        request.user = User()
        return request


class NotifyRateLimitTest(SimpleTestCase):
    @override_settings(RATELIMIT_NOTIFICATION_LIMITS=[(2, 60), (5, 60)])
    def test_allows_until_smallest_bucket(self) -> None:
        address = "mlrl-allow@example.com"

        # First two pass
        blocked, _ = rate_limit_notify(address)
        self.assertFalse(blocked)
        blocked, _ = rate_limit_notify(address)
        self.assertFalse(blocked)

        # Third is blocked due to the smallest bucket
        blocked, reason = rate_limit_notify(address)
        self.assertTrue(blocked)
        self.assertIn("2/60s", reason)

    @override_settings(RATELIMIT_NOTIFICATION_LIMITS=[(1, 60)])
    def test_separate_keys_are_independent(self) -> None:
        key_a = "mlrl-A@example.com"
        key_b = "mlrl-B@example.com"

        # A: first allowed, second blocked
        self.assertFalse(rate_limit_notify(key_a)[0])
        self.assertTrue(rate_limit_notify(key_a)[0])

        # B: still allowed independently
        self.assertFalse(rate_limit_notify(key_b)[0])


class NotifyRateLimitBehaviorTest(SimpleTestCase):
    def test_notify_revert_allows_one_more_then_blocks(self) -> None:
        limits = [(2, 60)]
        limiter = RateLimitNotify("mlrl-revert", limits)

        # Consume two allowed requests
        blocked, _ = limiter.is_limit_exceeded()
        self.assertFalse(blocked)
        blocked, _ = limiter.is_limit_exceeded()
        self.assertFalse(blocked)

        # Third should be blocked
        blocked, _ = limiter.is_limit_exceeded()
        self.assertTrue(blocked)

        # Revert once to add a single credit back
        limiter.revert()

        # One more should pass, then block again
        blocked, _ = limiter.is_limit_exceeded()
        self.assertFalse(blocked)
        blocked, _ = limiter.is_limit_exceeded()
        self.assertTrue(blocked)


class RateLimitHttpBehaviorTest(SimpleTestCase):
    def get_request(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "5.6.7.8"
        request.method = "POST"
        request.session = SessionStore()
        request._messages = default_storage(request)  # noqa: SLF001
        request.user = AnonymousUser()
        return request

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=60)
    def test_reset_rate_limit_clears_block(self) -> None:
        scope = "reset-case"
        request = self.get_request()
        self.assertTrue(check_rate_limit(scope, request))
        self.assertFalse(check_rate_limit(scope, request))
        reset_rate_limit(scope, request)
        self.assertTrue(check_rate_limit(scope, request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=60)
    def test_revert_rate_limit_adds_exactly_one_credit(self) -> None:
        scope = "revert-case-one"
        request = self.get_request()
        self.assertTrue(check_rate_limit(scope, request))
        self.assertFalse(check_rate_limit(scope, request))
        revert_rate_limit(scope, request)
        self.assertTrue(check_rate_limit(scope, request))
        self.assertFalse(check_rate_limit(scope, request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=2)
    def test_superuser_bypass(self) -> None:
        scope = "superuser-bypass"
        request = self.get_request()
        user = User()
        user.is_superuser = True
        request.user = user
        for _ in range(5):
            self.assertTrue(check_rate_limit(scope, request))

    @override_settings(RATELIMIT_ATTEMPTS=1, RATELIMIT_WINDOW=2, RATELIMIT_LOCKOUT=100)
    def test_lockout_keeps_blocked_without_time_advance(self) -> None:
        scope = "lockout-immediate"
        request = self.get_request()
        self.assertTrue(check_rate_limit(scope, request))
        self.assertFalse(check_rate_limit(scope, request))
        # Immediate subsequent call should still be blocked due to lockout
        self.assertFalse(check_rate_limit(scope, request))
