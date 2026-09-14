# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseBase
from django.test import SimpleTestCase, override_settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from weblate.api.apps import check_api_ratelimits
from weblate.api.middleware import ThrottlingMiddleware
from weblate.api.ratelimits import get_rate_policies
from weblate.api.spectacular import get_drf_settings
from weblate.api.throttling import AnonRateThrottle, UserRateThrottle
from weblate.auth.models import User
from weblate.middleware import ProxyMiddleware
from weblate.utils.environment import get_env_json

if TYPE_CHECKING:
    from rest_framework.request import Request


class RateLimitedView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (UserRateThrottle, AnonRateThrottle)

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


@override_settings(
    API_RATELIMIT_ANON="1/day",
    API_RATELIMIT_USER="1/hour",
    API_RATELIMIT_USER_OVERRIDES={},
    API_RATELIMIT_IP_OVERRIDES={},
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ApiRateLimitTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.factory = APIRequestFactory()
        self.enterContext(
            patch(
                "rest_framework.throttling.SimpleRateThrottle.timer", return_value=1000
            )
        )

    def request(
        self,
        address: str = "192.0.2.42",
        *,
        username: str | None = None,
        user_id: int = 1,
        forwarded: str | None = None,
        proxy: bool = False,
        protected: bool = False,
    ) -> HttpResponseBase:
        request = self.factory.get("/api/", REMOTE_ADDR=address)
        if forwarded is not None:
            request.META["HTTP_X_FORWARDED_FOR"] = forwarded
        force_authenticate(
            request,
            user=User(username=username, pk=user_id) if username else AnonymousUser(),
        )
        if proxy:
            ProxyMiddleware(lambda _request: Response()).process_request(request)
        permissions = (IsAuthenticated,) if protected else (AllowAny,)
        response = RateLimitedView.as_view(permission_classes=permissions)(request)
        result = ThrottlingMiddleware(lambda _request: response)(request)
        assert isinstance(result, HttpResponseBase)
        return result

    def test_defaults(self) -> None:
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-RateLimit-Limit"], "1")
        self.assertEqual(self.request().status_code, 429)
        self.assertEqual(self.request(username="automation").status_code, 200)
        self.assertEqual(self.request(username="automation").status_code, 429)

    @override_settings(API_RATELIMIT_ANON="2/day", API_RATELIMIT_USER="2/hour")
    def test_direct_settings(self) -> None:
        for username in (None, "automation"):
            with self.subTest(username=username):
                self.assertEqual(self.request(username=username).status_code, 200)
                self.assertEqual(self.request(username=username).status_code, 200)
                self.assertEqual(self.request(username=username).status_code, 429)

    def test_drf_rates_unused(self) -> None:
        drf = get_drf_settings(require_login=False)
        self.assertNotIn("DEFAULT_THROTTLE_RATES", drf)
        for rates in ({}, {"anon": "0/day", "user": "0/hour"}):
            with (
                self.subTest(rates=rates),
                override_settings(
                    REST_FRAMEWORK={**drf, "DEFAULT_THROTTLE_RATES": rates}
                ),
            ):
                cache.clear()
                self.assertEqual(self.request().status_code, 200)
                self.assertEqual(self.request(username="automation").status_code, 200)

    @override_settings(API_RATELIMIT_USER_OVERRIDES={"automation": "2/hour"})
    def test_user_override_headers(self) -> None:
        response = self.request(username="automation")
        self.assertEqual(response["X-RateLimit-Limit"], "2")
        self.assertEqual(response["X-RateLimit-Remaining"], "1")
        self.assertEqual(response["X-RateLimit-Reset"], "3600")
        self.assertEqual(
            self.request("192.0.2.43", username="automation").status_code, 200
        )
        response = self.request(username="automation")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "3600")

    @override_settings(API_RATELIMIT_IP_OVERRIDES={"192.0.2.0/24": "2/hour"})
    def test_ip_override_budgets(self) -> None:
        for address, username, user_id in (
            ("192.0.2.42", None, 1),
            ("192.0.2.43", None, 1),
            ("192.0.2.42", "automation", 1),
            ("192.0.2.42", "other", 2),
        ):
            with self.subTest(address=address, username=username):
                for _ in range(2):
                    response = self.request(address, username=username, user_id=user_id)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response["X-RateLimit-Limit"], "2")
                self.assertEqual(
                    self.request(
                        address, username=username, user_id=user_id
                    ).status_code,
                    429,
                )

    @override_settings(API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": None})
    def test_ip_exemption(self) -> None:
        for username in (None, "automation"):
            for _ in range(3):
                response = self.request(username=username)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-RateLimit-Limit", response)
        self.assertEqual(self.request(protected=True).status_code, 403)

    @override_settings(
        API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": None},
        API_RATELIMIT_USER_OVERRIDES={"automation": "1/hour"},
    )
    def test_user_limit_over_ip_exemption(self) -> None:
        self.assertEqual(self.request(username="automation").status_code, 200)
        self.assertEqual(self.request(username="automation").status_code, 429)

    @override_settings(
        API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": "1/hour"},
        API_RATELIMIT_USER_OVERRIDES={"automation": None},
    )
    def test_user_exemption_over_ip_limit(self) -> None:
        for _ in range(3):
            response = self.request(username="automation")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("X-RateLimit-Limit", response)

    @override_settings(
        API_RATELIMIT_IP_OVERRIDES={
            "192.0.2.0/24": None,
            "192.0.2.128/25": "2/hour",
            "192.0.2.255": "3/hour",
        }
    )
    def test_longest_prefix(self) -> None:
        self.assertNotIn("X-RateLimit-Limit", self.request("192.0.2.127"))
        self.assertEqual(self.request("192.0.2.128")["X-RateLimit-Limit"], "2")
        self.assertEqual(self.request("192.0.2.255")["X-RateLimit-Limit"], "3")
        self.assertEqual(self.request("192.0.3.0")["X-RateLimit-Limit"], "1")

    @override_settings(
        API_RATELIMIT_IP_OVERRIDES={"2001:db8::/48": "2/hour", "2001:db8::42": None}
    )
    def test_ipv6(self) -> None:
        self.assertNotIn("X-RateLimit-Limit", self.request("2001:0db8:0:0:0:0:0:42"))
        self.assertEqual(self.request("2001:db8::43").status_code, 200)
        self.assertEqual(self.request("2001:0db8:0:0:0:0:0:43").status_code, 200)
        self.assertEqual(self.request("2001:db8::43").status_code, 429)
        self.assertEqual(self.request("2001:db8:1::")["X-RateLimit-Limit"], "1")

    def test_policy_changes(self) -> None:
        self.assertEqual(self.request().status_code, 200)
        with override_settings(API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": "1/hour"}):
            self.assertEqual(self.request().status_code, 200)
            self.assertEqual(self.request().status_code, 429)
        with override_settings(API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": "2/day"}):
            self.assertEqual(self.request()["X-RateLimit-Remaining"], "1")
        self.assertEqual(self.request().status_code, 429)

    @override_settings(
        API_RATELIMIT_IP_OVERRIDES={"192.0.2.42": None},
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=-1,
    )
    def test_proxy(self) -> None:
        response = self.request("198.51.100.1", forwarded="192.0.2.42", proxy=True)
        self.assertNotIn("X-RateLimit-Limit", response)
        response = self.request("198.51.100.1", forwarded="192.0.2.42")
        self.assertEqual(response["X-RateLimit-Limit"], "1")
        response = self.request(
            "198.51.100.1", forwarded="192.0.2.42, 198.51.100.2", proxy=True
        )
        self.assertEqual(response["X-RateLimit-Limit"], "1")

    def test_invalid_configuration(self) -> None:
        invalid: list[tuple[str, object]] = [
            ("API_RATELIMIT_ANON", []),
            ("API_RATELIMIT_USER", "1/"),
            ("API_RATELIMIT_USER", "-1/hour"),
            ("API_RATELIMIT_USER", "1/year"),
            ("API_RATELIMIT_USER_OVERRIDES", []),
            ("API_RATELIMIT_IP_OVERRIDES", None),
            ("API_RATELIMIT_USER_OVERRIDES", {"": "1/hour"}),
            ("API_RATELIMIT_USER_OVERRIDES", {"automation": []}),
            ("API_RATELIMIT_USER_OVERRIDES", {"automation": "0/hour"}),
            ("API_RATELIMIT_IP_OVERRIDES", {"invalid": None}),
            ("API_RATELIMIT_IP_OVERRIDES", {"192.0.2.42/24": None}),
            ("API_RATELIMIT_IP_OVERRIDES", {"192.0.2.42": None, "192.0.2.42/32": None}),
        ]
        for name, value in invalid:
            with (
                self.subTest(name=name, value=value),
                override_settings(**{name: value}),
            ):
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    get_rate_policies()
                self.assertEqual(check_api_ratelimits()[0].id, "weblate.E050")
        self.assertEqual(check_api_ratelimits(), [])

    @override_settings(API_RATELIMIT_ANON=None, API_RATELIMIT_USER=None)
    def test_disabled_defaults(self) -> None:
        for _ in range(3):
            self.assertNotIn("X-RateLimit-Limit", self.request())

    @override_settings(API_RATELIMIT_ANON="0/day")
    def test_zero_default(self) -> None:
        self.assertEqual(self.request().status_code, 429)

    def test_docker_json(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    "WEBLATE_API_RATELIMIT_USER_OVERRIDES": '{"automation":"2/hour"}',
                    "WEBLATE_API_RATELIMIT_IP_OVERRIDES": '{"192.0.2.42":null}',
                },
            ),
            override_settings(
                API_RATELIMIT_USER_OVERRIDES=get_env_json(
                    "WEBLATE_API_RATELIMIT_USER_OVERRIDES", {}
                ),
                API_RATELIMIT_IP_OVERRIDES=get_env_json(
                    "WEBLATE_API_RATELIMIT_IP_OVERRIDES", {}
                ),
            ),
        ):
            self.assertNotIn("X-RateLimit-Limit", self.request())
            self.assertEqual(
                self.request(username="automation")["X-RateLimit-Limit"], "2"
            )
