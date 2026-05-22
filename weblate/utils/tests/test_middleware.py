# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import TestCase
from unittest.mock import patch

from django.http import HttpResponse
from django.http.request import HttpRequest
from django.test import RequestFactory
from django.test.utils import override_settings

from weblate.middleware import CSPBuilder, ProxyMiddleware

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class ProxyTest(TestCase):
    def get_response(self, request: AuthenticatedHttpRequest) -> str:
        self.assertEqual(request.META["REMOTE_ADDR"], "1.2.3.4")
        return "response"

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=False,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_direct(self) -> None:
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_proxy(self) -> None:
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "7.8.9.0"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=1,
    )
    def test_proxy_second(self) -> None:
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "7.8.9.0"
        request.META["HTTP_X_FORWARDED_FOR"] = "2.3.4.5, 1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_proxy_invalid(self) -> None:
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        request.META["HTTP_X_FORWARDED_FOR"] = "2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=-1,
    )
    def test_proxy_invalid_last(self) -> None:
        with patch("weblate.middleware.report_error") as mock_report_error:
            request = HttpRequest()
            request.META["REMOTE_ADDR"] = "1.2.3.4"
            request.META["HTTP_X_FORWARDED_FOR"] = "2.3.4, 1.2.3.4"
            middleware = ProxyMiddleware(self.get_response)
            self.assertEqual(middleware(request), "response")
            mock_report_error.assert_not_called()


class CSPBuilderTest(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(STATIC_URL="https://cdn.example.test/static/")
    def test_external_static_url_added_to_worker_src(self) -> None:
        request = self.factory.get("/")
        request.resolver_match = None

        builder = CSPBuilder(request, HttpResponse())

        self.assertIn("cdn.example.test", builder.directives["worker-src"])
