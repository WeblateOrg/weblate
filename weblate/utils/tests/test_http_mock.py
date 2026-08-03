# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import httpx2
from django.test import SimpleTestCase

from weblate.utils.requests import fetch_url
from weblate.utils.tests import http_mock


class HTTPMockTest(SimpleTestCase):
    @http_mock.activate
    def test_native_callback_and_recorded_request(self) -> None:
        def callback(request: httpx2.Request) -> httpx2.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://example.com/callback")
            self.assertEqual(request.content, b"request body")
            return httpx2.Response(201, json={"result": "created"})

        http_mock.register_callback(
            "POST",
            "https://example.com/callback",
            callback,
        )

        response = fetch_url(
            "post",
            "https://example.com/callback",
            content=b"request body",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"result": "created"})
        self.assertIsInstance(http_mock.calls[0].request, httpx2.Request)
        self.assertIs(http_mock.calls[0].response, response)

    @http_mock.activate
    def test_response_payload_validation_and_json_null(self) -> None:
        with self.assertRaisesRegex(TypeError, "Only one"):
            http_mock.register(
                "GET",
                "https://example.com/invalid",
                content=b"content",
                text="text",
            )
        http_mock.register(
            "GET",
            "https://example.com/null",
            json=None,
        )

        response = fetch_url("get", "https://example.com/null")

        self.assertEqual(response.content, b"null")
        self.assertEqual(response.headers["Content-Type"], "application/json")

    @http_mock.activate
    def test_route_sequence_replacement_and_removal(self) -> None:
        url = "https://example.com/sequence"
        first = http_mock.register("GET", url, text="first")
        second = http_mock.register("GET", url, text="second")

        self.assertEqual(fetch_url("get", url).text, "first")
        self.assertEqual(fetch_url("get", url).text, "second")
        self.assertEqual(len(first.calls), 1)
        self.assertEqual(len(second.calls), 1)

        http_mock.replace("GET", url, text="replacement")
        self.assertEqual(fetch_url("get", url).text, "replacement")

        http_mock.unregister("GET", url)
        with self.assertRaises(httpx2.ConnectError):
            fetch_url("get", url)

    @http_mock.activate
    def test_registered_exception_is_recorded(self) -> None:
        error = httpx2.ConnectTimeout("timed out")
        http_mock.register_exception(
            "GET",
            "https://example.com/timeout",
            error,
        )

        with self.assertRaises(httpx2.ConnectTimeout):
            fetch_url("get", "https://example.com/timeout")

        self.assertIs(http_mock.calls[0].response, error)

    @http_mock.activate
    def test_native_request_matchers(self) -> None:
        url = "https://example.com/match"
        http_mock.register(
            "POST",
            url,
            text="matched",
            match=[
                http_mock.json_params_matcher({"key": "value"}),
                http_mock.header_matcher({"X-Test": "expected"}),
            ],
        )
        http_mock.register("POST", url, text="fallback")

        response = fetch_url(
            "post",
            url,
            json={"key": "value"},
            headers={"X-Test": "expected"},
        )

        self.assertEqual(response.text, "matched")
