# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from time import sleep

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage import default_storage
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http.request import HttpRequest
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.auth.models import User
from weblate.utils.ratelimit import (
    check_rate_limit,
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
        request._messages = default_storage(request)  # noqa: SLF001
        request.user = AnonymousUser()
        return request

    def setUp(self) -> None:
        # Ensure no rate limits are there
        reset_rate_limit("test", self.get_request())

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
