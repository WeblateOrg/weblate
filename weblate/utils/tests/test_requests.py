# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx2
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.outbound import get_environment_proxy
from weblate.utils.requests import (
    PEER_IP_RESPONSE_ATTR,
    AsyncHTTPClient,
    HTTPClient,
    _get_response_peer_ip,
    _validate_response_peer,
    async_fetch_validated_url,
    fetch_url,
    fetch_validated_url,
    get_uri_error,
    open_restricted_asset_url,
)
from weblate.utils.tests import http_mock as responses


class TrackedSyncStream(httpx2.SyncByteStream):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __iter__(self):
        self.events.append("read")
        yield b"response-body"


class TrackedAsyncStream(httpx2.AsyncByteStream):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aiter__(self):
        self.events.append("read")
        yield b"response-body"


class TrackedRedirectSyncStream(TrackedSyncStream):
    def close(self) -> None:
        self.events.append("close")


class TrackedRedirectAsyncStream(TrackedAsyncStream):
    async def aclose(self) -> None:
        self.events.append("close")


class FetchURLTest(SimpleTestCase):
    def test_environment_proxy_uses_per_protocol_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "http_proxy": "http://http-proxy.example:8080",
                "https_proxy": "http://https-proxy.example:8080",
                "all_proxy": "http://generic-proxy.example:8080",
                "ftp_proxy": "http://ftp-proxy.example:8080",
                "no_proxy": "*",
            },
            clear=True,
        ):
            self.assertEqual(
                get_environment_proxy("http://example.com/source"),
                "http://http-proxy.example:8080",
            )
            self.assertEqual(
                get_environment_proxy("https://example.com/source"),
                "http://https-proxy.example:8080",
            )
            self.assertIsNone(get_environment_proxy("ftp://example.com/source"))

    def test_environment_proxy_does_not_use_all_proxy(self) -> None:
        with patch.dict(
            os.environ,
            {"all_proxy": "http://generic-proxy.example:8080"},
            clear=True,
        ):
            self.assertIsNone(get_environment_proxy("https://example.com/source"))

    @responses.activate
    def test_fetch_url_omits_null_form_values(self) -> None:
        responses.add(
            responses.POST,
            "https://gitlab.example.com/merge_requests",
            status=201,
        )

        fetch_url(
            "post",
            "https://gitlab.example.com/merge_requests",
            data={
                "source_branch": "weblate",
                "target_project_id": None,
            },
        )

        self.assertEqual(
            responses.calls[0].request.body,
            b"source_branch=weblate",
        )

    def test_http_client_does_not_read_streaming_redirect_body(self) -> None:
        events: list[str] = []

        def handle_request(request):
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={"Location": "/final"},
                    stream=TrackedRedirectSyncStream(events),
                )
            return httpx2.Response(200, content=b"final-response")

        client = HTTPClient(httpx2.MockTransport(handle_request))
        with client:
            response = client.request(
                "get",
                "https://example.com/redirect",
                stream=True,
            )
            try:
                self.assertEqual(response.read(), b"final-response")
                self.assertEqual(len(response.history), 1)
                self.assertTrue(response.history[0].is_closed)
            finally:
                response.close()

        self.assertEqual(events, ["close"])

    def test_async_http_client_does_not_read_streaming_redirect_body(self) -> None:
        events: list[str] = []

        def handle_request(request):
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={"Location": "/final"},
                    stream=TrackedRedirectAsyncStream(events),
                )
            return httpx2.Response(200, content=b"final-response")

        client = AsyncHTTPClient(httpx2.MockTransport(handle_request))

        async def make_request() -> httpx2.Response:
            async with client:
                response = await client.request(
                    "get",
                    "https://example.com/redirect",
                    stream=True,
                )
                try:
                    self.assertEqual(await response.aread(), b"final-response")
                    self.assertEqual(len(response.history), 1)
                    self.assertTrue(response.history[0].is_closed)
                    return response
                finally:
                    await response.aclose()

        asyncio.run(make_request())

        self.assertEqual(events, ["close"])

    def test_http_client_limits_streaming_redirects(self) -> None:
        events: list[str] = []

        def handle_request(_request):
            return httpx2.Response(
                302,
                headers={"Location": "/redirect"},
                stream=TrackedRedirectSyncStream(events),
            )

        client = HTTPClient(httpx2.MockTransport(handle_request))
        with (
            client,
            self.assertRaises(httpx2.TooManyRedirects),
        ):
            client.request(
                "get",
                "https://example.com/redirect",
                stream=True,
                max_redirects=1,
            )

        self.assertEqual(events, ["close", "close"])

    def test_http_client_keeps_redirect_limit_request_local(self) -> None:
        short_started = Event()
        long_started = Event()
        short_finished = Event()

        def handle_request(request):
            if request.url.path == "/short":
                short_started.set()
                if not long_started.wait(5):
                    msg = "Long request did not start."
                    raise RuntimeError(msg)
                return httpx2.Response(302, headers={"Location": "/short-final"})
            if request.url.path == "/long":
                long_started.set()
                if not short_finished.wait(5):
                    msg = "Short request did not finish."
                    raise RuntimeError(msg)
            return httpx2.Response(200)

        client = HTTPClient(httpx2.MockTransport(handle_request))

        def request_short_url() -> httpx2.Response:
            try:
                return client.request(
                    "get",
                    "https://example.com/short",
                    max_redirects=0,
                )
            finally:
                short_finished.set()

        with client, ThreadPoolExecutor(max_workers=2) as executor:
            short_result = executor.submit(request_short_url)
            self.assertTrue(short_started.wait(5))
            long_result = executor.submit(
                client.request,
                "get",
                "https://example.com/long",
                max_redirects=2,
            )

            with self.assertRaises(httpx2.TooManyRedirects):
                short_result.result(timeout=5)
            self.assertEqual(long_result.result(timeout=5).status_code, 200)

    def test_async_http_client_keeps_redirect_limit_request_local(self) -> None:
        async def run_requests() -> None:
            short_started = asyncio.Event()
            long_started = asyncio.Event()
            short_finished = asyncio.Event()

            async def handle_request(request):
                if request.url.path == "/short":
                    short_started.set()
                    await asyncio.wait_for(long_started.wait(), timeout=5)
                    return httpx2.Response(302, headers={"Location": "/short-final"})
                if request.url.path == "/long":
                    long_started.set()
                    await asyncio.wait_for(short_finished.wait(), timeout=5)
                return httpx2.Response(200)

            client = AsyncHTTPClient(httpx2.MockTransport(handle_request))

            async def request_short_url() -> httpx2.Response:
                try:
                    return await client.request(
                        "get",
                        "https://example.com/short",
                        max_redirects=0,
                    )
                finally:
                    short_finished.set()

            async with client:
                short_result = asyncio.create_task(request_short_url())
                await asyncio.wait_for(short_started.wait(), timeout=5)
                long_result = asyncio.create_task(
                    client.request(
                        "get",
                        "https://example.com/long",
                        max_redirects=2,
                    )
                )

                with self.assertRaises(httpx2.TooManyRedirects):
                    await short_result
                self.assertEqual((await long_result).status_code, 200)

        asyncio.run(run_requests())

    def test_async_http_client_uses_async_validator(self) -> None:
        request = httpx2.Request("GET", "https://example.com/data")
        response = httpx2.Response(
            200,
            request=request,
            content=b"response-body",
        )
        validators = MagicMock()
        validators.validate_async_request_url = AsyncMock(return_value=())
        client = AsyncHTTPClient(
            httpx2.MockTransport(lambda _request: response),
        )

        async def make_request() -> httpx2.Response:
            async with client:
                return await client.request(
                    "get",
                    "https://example.com/data",
                    validators=validators,
                )

        result = asyncio.run(make_request())

        self.assertEqual(result.content, b"response-body")
        validators.validate_async_request_url.assert_awaited_once_with(
            "https://example.com/data",
            used_proxy=False,
        )
        validators.validate_request_url.assert_not_called()


class OpenRestrictedAssetURLBehaviorTest(SimpleTestCase):
    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_follows_allowed_redirect(self) -> None:
        responses.add(
            responses.GET,
            "https://images.allowed.com/redirect-image.png",
            status=302,
            headers={"Location": "https://cdn.allowed.com/final-image.png"},
        )
        responses.add(
            responses.GET,
            "https://cdn.allowed.com/final-image.png",
            status=200,
            body=b"image-data",
        )

        with open_restricted_asset_url(
            "get",
            "https://images.allowed.com/redirect-image.png",
            allow_private_targets=True,
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(
            responses.calls[1].request.url,
            "https://cdn.allowed.com/final-image.png",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_blocks_disallowed_redirect(self) -> None:
        responses.add(
            responses.GET,
            "https://images.allowed.com/redirect-image.png",
            status=302,
            headers={"Location": "https://proof.example.com/final-image.png"},
        )
        responses.add(
            responses.GET,
            "https://proof.example.com/final-image.png",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://images.allowed.com/redirect-image.png",
                allow_private_targets=True,
            ),
        ):
            pass

        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://images.allowed.com/redirect-image.png",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_preserves_redirect_cookies(self) -> None:
        responses.add(
            responses.GET,
            "https://images.allowed.com/redirect-image.png",
            status=302,
            headers={
                "Location": "https://cdn.allowed.com/final-image.png",
                "Set-Cookie": "asset-token=allowed; Domain=.allowed.com; Path=/",
            },
        )
        responses.add(
            responses.GET,
            "https://cdn.allowed.com/final-image.png",
            status=200,
            body=b"image-data",
        )

        with open_restricted_asset_url(
            "get",
            "https://images.allowed.com/redirect-image.png",
            allow_private_targets=True,
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(
            responses.calls[1].request.headers["Cookie"],
            "asset-token=allowed",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_raises_validation_error_for_http_status(
        self,
    ) -> None:
        responses.add(
            responses.GET,
            "https://images.allowed.com/missing-image.png",
            status=404,
        )

        with (
            self.assertRaisesMessage(
                ValidationError,
                "Unable to download asset from the provided URL (HTTP status code: 404).",
            ),
            open_restricted_asset_url(
                "get",
                "https://images.allowed.com/missing-image.png",
                allow_private_targets=True,
            ),
        ):
            pass

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_raises_validation_error_for_redirect_status(
        self,
    ) -> None:
        responses.add(
            responses.GET,
            "https://images.allowed.com/redirect-image.png",
            status=301,
        )

        with (
            self.assertRaisesMessage(
                ValidationError,
                "Unable to download asset from the provided URL (HTTP status code: 301).",
            ),
            open_restricted_asset_url(
                "get",
                "https://images.allowed.com/redirect-image.png",
                allow_private_targets=True,
            ),
        ):
            pass


class OpenRestrictedAssetURLTest(SimpleTestCase):
    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_open_restricted_asset_url_blocks_private_target(
        self, mocked_getaddrinfo
    ) -> None:
        responses.add(
            responses.GET,
            "https://private.example.com/messages.html",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://private.example.com/messages.html",
            ),
        ):
            pass

        mocked_getaddrinfo.assert_called_once_with("private.example.com", None, type=1)
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="93.184.216.34")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [(0, 0, 0, "", ("93.184.216.34", 443))],
            [(0, 0, 0, "", ("127.0.0.1", 443))],
        ],
    )
    def test_open_restricted_asset_url_blocks_private_redirect(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/messages.html",
            status=302,
            headers={"Location": "https://private.example.com/messages.html"},
        )
        responses.add(
            responses.GET,
            "https://private.example.com/messages.html",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://public.example.com/messages.html",
                allow_private_targets=False,
            ),
        ):
            pass

        self.assertEqual(mocked_getaddrinfo.call_count, 2)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_open_restricted_asset_url_blocks_private_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/messages.html",
            status=200,
            body=b"should-not-be-read",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://public.example.com/messages.html",
                allow_private_targets=False,
            ),
        ):
            pass

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip", return_value=None)
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_open_restricted_asset_url_blocks_missing_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/messages.html",
            status=200,
            body=b"connection-close-response",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://public.example.com/messages.html",
                allow_private_targets=False,
            ),
        ):
            pass

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_open_restricted_asset_url_allows_allowlisted_private_target(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://private.example.com/messages.html",
            status=200,
            body=b"allowlisted-private-target",
        )

        with open_restricted_asset_url(
            "get",
            "https://private.example.com/messages.html",
            allow_private_targets=False,
            private_allowlist=["private.example.com"],
        ) as response:
            self.assertEqual(response.content, b"allowlisted-private-target")

        mocked_getaddrinfo.assert_not_called()
        mocked_get_peer.assert_not_called()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    @patch("weblate.utils.outbound.socket.getaddrinfo")
    def test_open_restricted_asset_url_blocks_disallowed_asset_domain(
        self, mocked_getaddrinfo
    ) -> None:
        responses.add(
            responses.GET,
            "https://blocked.example.com/messages.html",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            self.assertRaises(ValidationError),
            open_restricted_asset_url(
                "get",
                "https://blocked.example.com/messages.html",
                allow_private_targets=False,
            ),
        ):
            pass

        mocked_getaddrinfo.assert_not_called()
        self.assertEqual(len(responses.calls), 0)


class GetUriErrorTest(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()

    @responses.activate
    def test_get_uri_error_allows_internal_host_by_default(self) -> None:
        responses.add(
            responses.GET,
            "https://gitlab.intranet.example/project",
            status=200,
            body=b"ok",
        )

        self.assertIsNone(get_uri_error("https://gitlab.intranet.example/project"))

    @responses.activate
    @patch(
        "weblate.utils.requests._get_response_peer_ip",
        return_value="93.184.216.34",
    )
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [(0, 0, 0, "", ("93.184.216.34", 443))],
            [(0, 0, 0, "", ("127.0.0.1", 443))],
        ],
    )
    def test_get_uri_error_blocks_private_redirect(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=302,
            headers={"Location": "https://private.example.com/final"},
        )
        responses.add(
            responses.GET,
            "https://private.example.com/final",
            status=200,
            body=b"should-not-be-fetched",
        )

        expected_error = (
            "This URL is prohibited because it points to an internal or non-public "
            "address."
        )
        self.assertEqual(
            get_uri_error(
                "https://public.example.com/source", allow_private_targets=False
            ),
            expected_error,
        )

        self.assertEqual(mocked_getaddrinfo.call_count, 2)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch(
        "weblate.utils.requests._get_response_peer_ip",
        return_value="93.184.216.34",
    )
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [(0, 0, 0, "", ("93.184.216.34", 443))],
            [(0, 0, 0, "", ("127.0.0.1", 443))],
        ],
    )
    def test_get_uri_error_cache_is_scoped_by_private_target_policy(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=302,
            headers={"Location": "https://private.example.com/final"},
        )
        responses.add(
            responses.GET,
            "https://private.example.com/final",
            status=200,
            body=b"private-target",
        )

        expected_error = (
            "This URL is prohibited because it points to an internal or non-public "
            "address."
        )

        self.assertIsNone(get_uri_error("https://public.example.com/source"))
        self.assertEqual(
            get_uri_error(
                "https://public.example.com/source", allow_private_targets=False
            ),
            expected_error,
        )

        self.assertEqual(mocked_getaddrinfo.call_count, 2)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 3)

    @patch("weblate.utils.requests._probe_validated_url")
    def test_get_uri_error_flattens_validation_error(self, mocked_probe) -> None:
        mocked_probe.side_effect = ValidationError("This URL is prohibited")

        self.assertEqual(
            get_uri_error("https://example.com/source"),
            "This URL is prohibited",
        )


class FetchValidatedURLTest(SimpleTestCase):
    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [
                (0, 0, 0, "", ("93.184.216.34", 8443)),
                (0, 0, 0, "", ("2606:2800:220:1:248:1893:25c8:1946", 8443)),
            ],
            [(0, 0, 0, "", ("127.0.0.1", 8443))],
        ],
    )
    def test_fetch_validated_url_pins_validated_address(
        self, mocked_getaddrinfo
    ) -> None:
        url = "https://public.example.com:8443/source"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"pinned",
        )

        response = fetch_validated_url(
            "get",
            url,
            allow_private_targets=False,
        )

        self.assertEqual(response.content, b"pinned")
        self.assertEqual(str(response.url), url)
        self.assertEqual(
            responses.calls[0].request.transport_url,
            "https://93.184.216.34:8443/source",
        )
        self.assertEqual(
            responses.calls[0].request.headers["Host"],
            "public.example.com:8443",
        )
        self.assertEqual(
            responses.calls[0].request.extensions["sni_hostname"],
            "public.example.com",
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[
            (0, 0, 0, "", ("2606:2800:220:1:248:1893:25c8:1946", 443)),
            (0, 0, 0, "", ("93.184.216.34", 443)),
        ],
    )
    def test_fetch_validated_url_falls_back_to_validated_address(
        self, mocked_getaddrinfo
    ) -> None:
        url = "https://public.example.com/source"
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectError("IPv6 route unavailable"),
        )
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"fallback",
        )

        with patch(
            "weblate.utils.requests.monotonic",
            side_effect=[0, 0, 0.25, 0.25],
        ):
            response = fetch_validated_url(
                "get",
                url,
                allow_private_targets=False,
            )

        self.assertEqual(response.content, b"fallback")
        self.assertEqual(
            [call.request.transport_url for call in responses.calls],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in responses.calls],
            [0.25, 0.25],
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[
            (0, 0, 0, "", ("2606:2800:220:1:248:1893:25c8:1946", 443)),
            (0, 0, 0, "", ("93.184.216.34", 443)),
        ],
    )
    def test_fetch_validated_url_retries_slow_validated_address(
        self, mocked_getaddrinfo
    ) -> None:
        url = "https://public.example.com/source"
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectTimeout("IPv6 probe timed out"),
        )
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectTimeout("IPv4 probe timed out"),
        )
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"slow-fallback",
        )

        with patch(
            "weblate.utils.requests.monotonic",
            side_effect=[0, 0, 0.25, 0.25, 0.25, 0.25],
        ):
            response = fetch_validated_url(
                "get",
                url,
                allow_private_targets=False,
            )

        self.assertEqual(response.content, b"slow-fallback")
        self.assertEqual(
            [call.request.transport_url for call in responses.calls],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in responses.calls],
            [0.25, 0.25, 4.75],
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @responses.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        return_value=("93.184.216.34",),
    )
    def test_async_fetch_validated_url_pins_validated_address(
        self, mocked_resolve
    ) -> None:
        url = "https://public.example.com/source"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"async-pinned",
        )

        response = asyncio.run(
            async_fetch_validated_url(
                "get",
                url,
                allow_private_targets=False,
            )
        )

        self.assertEqual(response.content, b"async-pinned")
        self.assertEqual(str(response.url), url)
        self.assertEqual(
            responses.calls[0].request.transport_url,
            "https://93.184.216.34/source",
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @responses.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        side_effect=ValidationError("This URL is prohibited"),
    )
    def test_async_fetch_validated_url_blocks_private_target_by_default(
        self, mocked_resolve
    ) -> None:
        responses.add(
            responses.GET,
            "https://private.example.com/source",
            status=200,
            body=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            asyncio.run(
                async_fetch_validated_url(
                    "get",
                    "https://private.example.com/source",
                )
            )

        mocked_resolve.assert_awaited_once_with(
            "private.example.com", allow_private_targets=False
        )
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        return_value=(
            "2606:2800:220:1:248:1893:25c8:1946",
            "93.184.216.34",
        ),
    )
    def test_async_fetch_validated_url_falls_back_to_validated_address(
        self, mocked_resolve
    ) -> None:
        url = "https://public.example.com/source"
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectTimeout("IPv6 route timed out"),
        )
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"async-fallback",
        )

        with patch(
            "weblate.utils.requests.monotonic",
            side_effect=[0, 0, 0.25, 0.25],
        ):
            response = asyncio.run(
                async_fetch_validated_url(
                    "get",
                    url,
                    allow_private_targets=False,
                )
            )

        self.assertEqual(response.content, b"async-fallback")
        self.assertEqual(
            [call.request.transport_url for call in responses.calls],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in responses.calls],
            [0.25, 0.25],
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @responses.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        return_value=(
            "2606:2800:220:1:248:1893:25c8:1946",
            "93.184.216.34",
        ),
    )
    def test_async_fetch_validated_url_retries_slow_validated_address(
        self, mocked_resolve
    ) -> None:
        url = "https://public.example.com/source"
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectTimeout("IPv6 probe timed out"),
        )
        responses.add(
            responses.GET,
            url,
            body=httpx2.ConnectTimeout("IPv4 probe timed out"),
        )
        responses.add(
            responses.GET,
            url,
            status=200,
            body=b"async-slow-fallback",
        )

        with patch(
            "weblate.utils.requests.monotonic",
            side_effect=[0, 0, 0.25, 0.25, 0.25, 0.25],
        ):
            response = asyncio.run(
                async_fetch_validated_url(
                    "get",
                    url,
                    allow_private_targets=False,
                )
            )

        self.assertEqual(response.content, b"async-slow-fallback")
        self.assertEqual(
            [call.request.transport_url for call in responses.calls],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in responses.calls],
            [0.25, 0.25, 4.75],
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_uses_idna_sni_name(self, mocked_getaddrinfo) -> None:
        responses.add(
            responses.GET,
            "https://xn--fa-hia.de/source",
            status=200,
            body=b"idna",
        )

        response = fetch_validated_url(
            "get",
            "https://faß.de/source",
            allow_private_targets=False,
        )

        self.assertEqual(response.content, b"idna")
        self.assertEqual(
            responses.calls[0].request.extensions["sni_hostname"],
            "xn--fa-hia.de",
        )
        mocked_getaddrinfo.assert_called_once_with("xn--fa-hia.de", None, type=1)

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_keeps_logical_url_for_relative_redirect(
        self, mocked_getaddrinfo
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=302,
            headers={"Location": "/final"},
        )
        responses.add(
            responses.GET,
            "https://public.example.com/final",
            status=200,
            body=b"redirected",
        )

        response = fetch_validated_url(
            "get",
            "https://public.example.com/source",
            allow_private_targets=False,
        )

        self.assertEqual(response.content, b"redirected")
        self.assertEqual(str(response.url), "https://public.example.com/final")
        self.assertEqual(
            [str(item.url) for item in response.history],
            ["https://public.example.com/source"],
        )
        self.assertEqual(
            [call.request.transport_url for call in responses.calls],
            [
                "https://93.184.216.34/source",
                "https://93.184.216.34/final",
            ],
        )
        self.assertEqual(mocked_getaddrinfo.call_count, 2)

    @responses.activate
    def test_fetch_validated_url_strips_auth_on_cross_origin_redirect(self) -> None:
        recorded_headers: list[dict[str, str]] = []

        def redirect(request):
            recorded_headers.append(dict(request.headers))
            return (
                302,
                {"Location": "https://other.example.com/final"},
                b"",
            )

        def final(request):
            recorded_headers.append(dict(request.headers))
            return 200, {}, b"ok"

        responses.add_callback(
            responses.GET,
            "https://public.example.com/source",
            callback=redirect,
        )
        responses.add_callback(
            responses.GET,
            "https://other.example.com/final",
            callback=final,
        )

        fetch_validated_url(
            "get",
            "https://public.example.com/source",
            headers={"Authorization": "Bearer secret"},
            auth=("user", "pass"),
            allow_redirects=True,
            allow_private_targets=True,
        )

        self.assertEqual(len(recorded_headers), 2)
        self.assertIn("authorization", recorded_headers[0])
        self.assertNotIn("authorization", recorded_headers[1])

    @responses.activate
    def test_fetch_validated_url_preserves_delete_method_on_301_redirect(self) -> None:
        recorded_calls: list[tuple[str, bytes | None]] = []

        def redirect(request):
            recorded_calls.append((request.method, request.body))
            return (
                301,
                {"Location": "https://public.example.com/final"},
                b"",
            )

        def final(request):
            recorded_calls.append((request.method, request.body))
            return 200, {}, b"ok"

        responses.add_callback(
            responses.DELETE,
            "https://public.example.com/source",
            callback=redirect,
        )
        responses.add_callback(
            responses.DELETE,
            "https://public.example.com/final",
            callback=final,
        )

        fetch_validated_url(
            "delete",
            "https://public.example.com/source",
            allow_redirects=True,
            allow_private_targets=True,
            data=b"payload",
        )

        self.assertEqual(
            recorded_calls,
            [("DELETE", b"payload"), ("DELETE", b"payload")],
        )

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_fetch_validated_url_blocks_private_target_by_default(
        self, mocked_getaddrinfo
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=200,
            body=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
            )

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="93.184.216.34")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [(0, 0, 0, "", ("93.184.216.34", 443))],
            [(0, 0, 0, "", ("127.0.0.1", 443))],
        ],
    )
    def test_fetch_validated_url_blocks_private_redirect(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=302,
            headers={"Location": "https://private.example.com/final"},
        )
        responses.add(
            responses.GET,
            "https://private.example.com/final",
            status=200,
            body=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        self.assertEqual(mocked_getaddrinfo.call_count, 2)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_blocks_private_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=200,
            body=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_fetch_validated_url_allows_allowlisted_private_target(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://private.example/source",
            status=200,
            body=b"allowlisted-private-target",
        )

        response = fetch_validated_url(
            "get",
            "https://private.example/source",
            allow_private_targets=False,
            private_allowlist=["private.example"],
        )

        self.assertEqual(response.content, b"allowlisted-private-target")
        mocked_getaddrinfo.assert_not_called()
        mocked_get_peer.assert_not_called()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch(
        "weblate.utils.requests._get_response_peer_ip",
        side_effect=["93.184.216.34", "127.0.0.1"],
    )
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=[
            [(0, 0, 0, "", ("93.184.216.34", 443))],
            [(0, 0, 0, "", ("127.0.0.1", 443))],
        ],
    )
    def test_fetch_validated_url_allows_redirect_to_allowlisted_private_target(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=302,
            headers={"Location": "https://private.example/final"},
        )
        responses.add(
            responses.GET,
            "https://private.example/final",
            status=200,
            body=b"allowlisted-private-redirect",
        )

        response = fetch_validated_url(
            "get",
            "https://public.example.com/source",
            allow_private_targets=False,
            private_allowlist=["private.example"],
        )

        self.assertEqual(response.content, b"allowlisted-private-redirect")
        self.assertEqual(mocked_getaddrinfo.call_count, 1)
        self.assertEqual(mocked_get_peer.call_count, 1)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_skips_peer_validation_through_proxy(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=200,
            body=b"fetched-via-proxy",
        )

        with patch.dict(
            os.environ,
            {
                "HTTPS_PROXY": "http://127.0.0.1:8080",
                "HTTP_PROXY": "",
                "ALL_PROXY": "",
                "NO_PROXY": "",
            },
        ):
            response = fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        self.assertEqual(response.content, b"fetched-via-proxy")
        mocked_getaddrinfo.assert_not_called()
        mocked_get_peer.assert_not_called()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_fetch_validated_url_allows_proxy_resolved_hostname(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "https://public.example.com/source",
            status=200,
            body=b"resolved-by-proxy",
        )

        with patch.dict(
            os.environ,
            {
                "HTTPS_PROXY": "http://127.0.0.1:8080",
                "HTTP_PROXY": "",
                "ALL_PROXY": "",
                "NO_PROXY": "",
            },
        ):
            response = fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        self.assertEqual(response.content, b"resolved-by-proxy")
        mocked_getaddrinfo.assert_not_called()
        mocked_get_peer.assert_not_called()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_fetch_validated_url_allows_allowlisted_hostname_through_proxy(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        responses.add(
            responses.GET,
            "http://ollama/api/tags",
            status=200,
            body=b'{"models":[]}',
        )

        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:8080",
                "HTTPS_PROXY": "",
                "ALL_PROXY": "",
                "NO_PROXY": "",
            },
        ):
            response = fetch_validated_url(
                "get",
                "http://ollama/api/tags",
                allow_private_targets=False,
                private_allowlist=["ollama"],
            )

        self.assertEqual(response.content, b'{"models":[]}')
        mocked_getaddrinfo.assert_not_called()
        mocked_get_peer.assert_not_called()
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_fetch_validated_url_blocks_localhost_alias_through_proxy(self) -> None:
        responses.add(
            responses.GET,
            "http://localhost./source",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            patch.dict(
                os.environ,
                {
                    "HTTP_PROXY": "http://127.0.0.1:8080",
                    "HTTPS_PROXY": "",
                    "ALL_PROXY": "",
                    "NO_PROXY": "",
                },
            ),
            self.assertRaises(ValidationError),
        ):
            fetch_validated_url(
                "get",
                "http://localhost./source",
                allow_private_targets=False,
            )

        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_fetch_validated_url_blocks_shorthand_loopback_through_proxy(self) -> None:
        responses.add(
            responses.GET,
            "http://127.1/source",
            status=200,
            body=b"should-not-be-fetched",
        )

        with (
            patch.dict(
                os.environ,
                {
                    "HTTP_PROXY": "http://127.0.0.1:8080",
                    "HTTPS_PROXY": "",
                    "ALL_PROXY": "",
                    "NO_PROXY": "",
                },
            ),
            self.assertRaises(ValidationError),
        ):
            fetch_validated_url(
                "get",
                "http://127.1/source",
                allow_private_targets=False,
            )

        self.assertEqual(len(responses.calls), 0)

    @patch("weblate.utils.requests._get_response_peer_ip", return_value=None)
    def test_http_request_fails_when_peer_ip_is_unavailable(
        self, mocked_get_peer
    ) -> None:
        response = Mock()
        response.url = "https://public.example.com/source"

        with self.assertRaises(ValidationError):
            _validate_response_peer(
                response,
                allow_private_targets=False,
                used_proxy=False,
            )

        mocked_get_peer.assert_called_once_with(response)

    def test_get_response_peer_ip_uses_cached_peer_after_socket_release(self) -> None:
        response = Mock()
        response.raw.connection.sock = None
        setattr(response, PEER_IP_RESPONSE_ATTR, "93.184.216.34")

        self.assertEqual(_get_response_peer_ip(response), "93.184.216.34")

    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    def test_validate_response_peer_skips_allowlisted_hostname(
        self, mocked_get_peer
    ) -> None:
        response = Mock()
        response.url = "https://private.example/source"

        _validate_response_peer(
            response,
            allow_private_targets=False,
            private_allowlist=["private.example"],
            used_proxy=False,
        )

        mocked_get_peer.assert_not_called()
