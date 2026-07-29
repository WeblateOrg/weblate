# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx2
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.outbound import get_environment_proxy
from weblate.utils.requests import (
    PEER_IP_RESPONSE_ATTR,
    _get_response_peer_ip,
    _validate_response_peer,
    async_fetch_url,
    async_fetch_validated_url,
    create_async_http_client,
    fetch_url,
    fetch_validated_url,
    get_uri_error,
    open_restricted_asset_url,
)
from weblate.utils.tests import http_mock


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

    def test_fetch_url_does_not_read_redirect_body(self) -> None:
        events: list[str] = []

        def handle_request(request):
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={"Location": "/final"},
                    stream=TrackedRedirectSyncStream(events),
                )
            return httpx2.Response(200, content=b"final-response")

        with patch(
            "weblate.utils.requests._TEST_TRANSPORT.transport",
            httpx2.MockTransport(handle_request),
        ):
            response = fetch_url("get", "https://example.com/redirect")

        self.assertEqual(response.content, b"final-response")
        self.assertEqual(len(response.history), 1)
        self.assertTrue(response.history[0].is_closed)
        self.assertEqual(events, ["close"])

    def test_async_fetch_url_does_not_read_redirect_body(self) -> None:
        events: list[str] = []

        def handle_request(request):
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={"Location": "/final"},
                    stream=TrackedRedirectAsyncStream(events),
                )
            return httpx2.Response(200, content=b"final-response")

        async def make_request() -> httpx2.Response:
            return await async_fetch_url(
                "get",
                "https://example.com/redirect",
            )

        with patch(
            "weblate.utils.requests._TEST_TRANSPORT.transport",
            httpx2.MockTransport(handle_request),
        ):
            response = asyncio.run(make_request())

        self.assertEqual(response.content, b"final-response")
        self.assertEqual(len(response.history), 1)
        self.assertTrue(response.history[0].is_closed)
        self.assertEqual(events, ["close"])

    def test_fetch_url_limits_redirects(self) -> None:
        events: list[str] = []

        def handle_request(_request):
            return httpx2.Response(
                302,
                headers={"Location": "/redirect"},
                stream=TrackedRedirectSyncStream(events),
            )

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                httpx2.MockTransport(handle_request),
            ),
            self.assertRaises(httpx2.TooManyRedirects),
        ):
            fetch_url("get", "https://example.com/redirect")

        self.assertEqual(events, ["close"] * 6)

    @http_mock.activate
    def test_fetch_url_does_not_follow_redirects_when_disabled(self) -> None:
        http_mock.register(
            "GET",
            "https://example.com/redirect",
            status_code=302,
            headers={"Location": "/final"},
        )

        response = fetch_url(
            "get",
            "https://example.com/redirect",
            follow_redirects=False,
            raise_for_status=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.history, [])
        self.assertEqual(len(http_mock.calls), 1)

    def test_async_http_client_uses_async_validator(self) -> None:
        request = httpx2.Request("GET", "https://example.com/data")
        response = httpx2.Response(
            200,
            request=request,
            content=b"response-body",
        )
        validators = MagicMock()
        validators.validate_async_request_url = AsyncMock(return_value=())
        client = create_async_http_client(
            transport=httpx2.MockTransport(lambda _request: response),
            validators=validators,
        )

        async def make_request() -> httpx2.Response:
            async with client:
                return await client.request(
                    "get",
                    "https://example.com/data",
                )

        result = asyncio.run(make_request())

        self.assertEqual(result.content, b"response-body")
        validators.validate_async_request_url.assert_awaited_once_with(
            "https://example.com/data",
            used_proxy=False,
        )
        validators.validate_request_url.assert_not_called()


class OpenRestrictedAssetURLBehaviorTest(SimpleTestCase):
    def test_open_restricted_asset_url_does_not_read_redirect_body(self) -> None:
        events: list[str] = []

        def handle_request(request):
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={"Location": "/final"},
                    stream=TrackedRedirectSyncStream(events),
                )
            return httpx2.Response(200, content=b"final-response")

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                httpx2.MockTransport(handle_request),
            ),
            patch(
                "weblate.utils.requests.RestrictedAssetRedirectValidators.validate_request_url",
                return_value=(),
            ),
            open_restricted_asset_url(
                "get",
                "https://example.com/redirect",
                allow_private_targets=True,
            ) as response,
        ):
            self.assertEqual(response.read(), b"final-response")
            self.assertEqual(len(response.history), 1)
            self.assertTrue(response.history[0].is_closed)

        self.assertEqual(events, ["close"])

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_follows_allowed_redirect(self) -> None:
        http_mock.register(
            "GET",
            "https://images.allowed.com/redirect-image.png",
            status_code=302,
            headers={"Location": "https://cdn.allowed.com/final-image.png"},
        )
        http_mock.register(
            "GET",
            "https://cdn.allowed.com/final-image.png",
            status_code=200,
            content=b"image-data",
        )

        with open_restricted_asset_url(
            "get",
            "https://images.allowed.com/redirect-image.png",
            allow_private_targets=True,
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(len(http_mock.calls), 2)
        self.assertEqual(
            http_mock.calls[1].request.url,
            "https://cdn.allowed.com/final-image.png",
        )

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_blocks_disallowed_redirect(self) -> None:
        http_mock.register(
            "GET",
            "https://images.allowed.com/redirect-image.png",
            status_code=302,
            headers={"Location": "https://proof.example.com/final-image.png"},
        )
        http_mock.register(
            "GET",
            "https://proof.example.com/final-image.png",
            status_code=200,
            content=b"should-not-be-fetched",
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

        self.assertEqual(len(http_mock.calls), 1)
        self.assertEqual(
            http_mock.calls[0].request.url,
            "https://images.allowed.com/redirect-image.png",
        )

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_preserves_redirect_cookies(self) -> None:
        http_mock.register(
            "GET",
            "https://images.allowed.com/redirect-image.png",
            status_code=302,
            headers={
                "Location": "https://cdn.allowed.com/final-image.png",
                "Set-Cookie": "asset-token=allowed; Domain=.allowed.com; Path=/",
            },
        )
        http_mock.register(
            "GET",
            "https://cdn.allowed.com/final-image.png",
            status_code=200,
            content=b"image-data",
        )

        with open_restricted_asset_url(
            "get",
            "https://images.allowed.com/redirect-image.png",
            allow_private_targets=True,
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(
            http_mock.calls[1].request.headers["Cookie"],
            "asset-token=allowed",
        )

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_raises_validation_error_for_http_status(
        self,
    ) -> None:
        http_mock.register(
            "GET",
            "https://images.allowed.com/missing-image.png",
            status_code=404,
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

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_restricted_asset_url_raises_validation_error_for_redirect_status(
        self,
    ) -> None:
        http_mock.register(
            "GET",
            "https://images.allowed.com/redirect-image.png",
            status_code=301,
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
    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_open_restricted_asset_url_blocks_private_target(
        self, mocked_getaddrinfo
    ) -> None:
        http_mock.register(
            "GET",
            "https://private.example.com/messages.html",
            status_code=200,
            content=b"should-not-be-fetched",
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
        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
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
        http_mock.register(
            "GET",
            "https://public.example.com/messages.html",
            status_code=302,
            headers={"Location": "https://private.example.com/messages.html"},
        )
        http_mock.register(
            "GET",
            "https://private.example.com/messages.html",
            status_code=200,
            content=b"should-not-be-fetched",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_open_restricted_asset_url_blocks_private_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/messages.html",
            status_code=200,
            content=b"should-not-be-read",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip", return_value=None)
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_open_restricted_asset_url_blocks_missing_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/messages.html",
            status_code=200,
            content=b"connection-close-response",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=["*"])
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_open_restricted_asset_url_allows_allowlisted_private_target(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://private.example.com/messages.html",
            status_code=200,
            content=b"allowlisted-private-target",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    @patch("weblate.utils.outbound.socket.getaddrinfo")
    def test_open_restricted_asset_url_blocks_disallowed_asset_domain(
        self, mocked_getaddrinfo
    ) -> None:
        http_mock.register(
            "GET",
            "https://blocked.example.com/messages.html",
            status_code=200,
            content=b"should-not-be-fetched",
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
        self.assertEqual(len(http_mock.calls), 0)


class GetUriErrorTest(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()

    @http_mock.activate
    def test_get_uri_error_allows_internal_host_by_default(self) -> None:
        http_mock.register(
            "GET",
            "https://gitlab.intranet.example/project",
            status_code=200,
            content=b"ok",
        )

        self.assertIsNone(get_uri_error("https://gitlab.intranet.example/project"))

    @http_mock.activate
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
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=302,
            headers={"Location": "https://private.example.com/final"},
        )
        http_mock.register(
            "GET",
            "https://private.example.com/final",
            status_code=200,
            content=b"should-not-be-fetched",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
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
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=302,
            headers={"Location": "https://private.example.com/final"},
        )
        http_mock.register(
            "GET",
            "https://private.example.com/final",
            status_code=200,
            content=b"private-target",
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
        self.assertEqual(len(http_mock.calls), 3)

    @patch("weblate.utils.requests._probe_validated_url")
    def test_get_uri_error_flattens_validation_error(self, mocked_probe) -> None:
        mocked_probe.side_effect = ValidationError("This URL is prohibited")

        self.assertEqual(
            get_uri_error("https://example.com/source"),
            "This URL is prohibited",
        )


class FetchValidatedURLTest(SimpleTestCase):
    @http_mock.activate
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
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"pinned",
        )

        response = fetch_validated_url(
            "get",
            url,
            allow_private_targets=False,
        )

        self.assertEqual(response.content, b"pinned")
        self.assertEqual(str(response.url), url)
        self.assertEqual(
            str(http_mock.get_transport_url(http_mock.calls[0].request)),
            "https://93.184.216.34:8443/source",
        )
        self.assertEqual(
            http_mock.calls[0].request.headers["Host"],
            "public.example.com:8443",
        )
        self.assertEqual(
            http_mock.calls[0].request.extensions["sni_hostname"],
            "public.example.com",
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @http_mock.activate
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
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectError("IPv6 route unavailable"),
        )
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"fallback",
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
            [
                str(http_mock.get_transport_url(call.request))
                for call in http_mock.calls
            ],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in http_mock.calls],
            [0.25, 0.25],
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @http_mock.activate
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
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectTimeout("IPv6 probe timed out"),
        )
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectTimeout("IPv4 probe timed out"),
        )
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"slow-fallback",
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
            [
                str(http_mock.get_transport_url(call.request))
                for call in http_mock.calls
            ],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in http_mock.calls],
            [0.25, 0.25, 4.75],
        )
        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)

    @http_mock.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        return_value=("93.184.216.34",),
    )
    def test_async_fetch_validated_url_pins_validated_address(
        self, mocked_resolve
    ) -> None:
        url = "https://public.example.com/source"
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"async-pinned",
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
            str(http_mock.get_transport_url(http_mock.calls[0].request)),
            "https://93.184.216.34/source",
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @http_mock.activate
    @patch(
        "weblate.utils.requests.async_resolve_runtime_hostname",
        new_callable=AsyncMock,
        side_effect=ValidationError("This URL is prohibited"),
    )
    def test_async_fetch_validated_url_blocks_private_target_by_default(
        self, mocked_resolve
    ) -> None:
        http_mock.register(
            "GET",
            "https://private.example.com/source",
            status_code=200,
            content=b"should-not-be-fetched",
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
        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
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
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectTimeout("IPv6 route timed out"),
        )
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"async-fallback",
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
            [
                str(http_mock.get_transport_url(call.request))
                for call in http_mock.calls
            ],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in http_mock.calls],
            [0.25, 0.25],
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @http_mock.activate
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
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectTimeout("IPv6 probe timed out"),
        )
        http_mock.register_exception(
            "GET",
            url,
            exception=httpx2.ConnectTimeout("IPv4 probe timed out"),
        )
        http_mock.register(
            "GET",
            url,
            status_code=200,
            content=b"async-slow-fallback",
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
            [
                str(http_mock.get_transport_url(call.request))
                for call in http_mock.calls
            ],
            [
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
                "https://93.184.216.34/source",
                "https://[2606:2800:220:1:248:1893:25c8:1946]/source",
            ],
        )
        self.assertEqual(
            [call.request.extensions["timeout"]["connect"] for call in http_mock.calls],
            [0.25, 0.25, 4.75],
        )
        mocked_resolve.assert_awaited_once_with(
            "public.example.com", allow_private_targets=False
        )

    @http_mock.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_uses_idna_sni_name(self, mocked_getaddrinfo) -> None:
        http_mock.register(
            "GET",
            "https://xn--fa-hia.de/source",
            status_code=200,
            content=b"idna",
        )

        response = fetch_validated_url(
            "get",
            "https://faß.de/source",
            allow_private_targets=False,
        )

        self.assertEqual(response.content, b"idna")
        self.assertEqual(
            http_mock.calls[0].request.extensions["sni_hostname"],
            "xn--fa-hia.de",
        )
        mocked_getaddrinfo.assert_called_once_with("xn--fa-hia.de", None, type=1)

    @http_mock.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_keeps_logical_url_for_relative_redirect(
        self, mocked_getaddrinfo
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=302,
            headers={"Location": "/final"},
        )
        http_mock.register(
            "GET",
            "https://public.example.com/final",
            status_code=200,
            content=b"redirected",
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
            [
                str(http_mock.get_transport_url(call.request))
                for call in http_mock.calls
            ],
            [
                "https://93.184.216.34/source",
                "https://93.184.216.34/final",
            ],
        )
        self.assertEqual(mocked_getaddrinfo.call_count, 2)

    @http_mock.activate
    def test_fetch_validated_url_strips_auth_on_cross_origin_redirect(self) -> None:
        recorded_headers: list[dict[str, str]] = []

        def redirect(request):
            recorded_headers.append(dict(request.headers))
            return httpx2.Response(
                302,
                headers={"Location": "https://other.example.com/final"},
                content=b"",
            )

        def final(request):
            recorded_headers.append(dict(request.headers))
            return httpx2.Response(200, headers={}, content=b"ok")

        http_mock.register_callback(
            "GET",
            "https://public.example.com/source",
            callback=redirect,
        )
        http_mock.register_callback(
            "GET",
            "https://other.example.com/final",
            callback=final,
        )

        fetch_validated_url(
            "get",
            "https://public.example.com/source",
            headers={"Authorization": "Bearer secret"},
            auth=("user", "pass"),
            follow_redirects=True,
            allow_private_targets=True,
        )

        self.assertEqual(len(recorded_headers), 2)
        self.assertIn("authorization", recorded_headers[0])
        self.assertNotIn("authorization", recorded_headers[1])

    @http_mock.activate
    def test_fetch_validated_url_preserves_delete_method_on_301_redirect(self) -> None:
        recorded_calls: list[tuple[str, bytes]] = []

        def redirect(request):
            recorded_calls.append((request.method, request.content))
            return httpx2.Response(
                301,
                headers={"Location": "https://public.example.com/final"},
                content=b"",
            )

        def final(request):
            recorded_calls.append((request.method, request.content))
            return httpx2.Response(200, headers={}, content=b"ok")

        http_mock.register_callback(
            "DELETE",
            "https://public.example.com/source",
            callback=redirect,
        )
        http_mock.register_callback(
            "DELETE",
            "https://public.example.com/final",
            callback=final,
        )

        fetch_validated_url(
            "delete",
            "https://public.example.com/source",
            follow_redirects=True,
            allow_private_targets=True,
            content=b"payload",
        )

        self.assertEqual(
            recorded_calls,
            [("DELETE", b"payload"), ("DELETE", b"payload")],
        )

    @http_mock.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_fetch_validated_url_blocks_private_target_by_default(
        self, mocked_getaddrinfo
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=200,
            content=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
            )

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
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
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=302,
            headers={"Location": "https://private.example.com/final"},
        )
        http_mock.register(
            "GET",
            "https://private.example.com/final",
            status_code=200,
            content=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        self.assertEqual(mocked_getaddrinfo.call_count, 2)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_blocks_private_peer_after_public_dns(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=200,
            content=b"should-not-be-fetched",
        )

        with self.assertRaises(ValidationError):
            fetch_validated_url(
                "get",
                "https://public.example.com/source",
                allow_private_targets=False,
            )

        mocked_getaddrinfo.assert_called_once_with("public.example.com", None, type=1)
        mocked_get_peer.assert_called_once()
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @patch("weblate.utils.requests._get_response_peer_ip", return_value="127.0.0.1")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_fetch_validated_url_allows_allowlisted_private_target(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://private.example/source",
            status_code=200,
            content=b"allowlisted-private-target",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
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
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=302,
            headers={"Location": "https://private.example/final"},
        )
        http_mock.register(
            "GET",
            "https://private.example/final",
            status_code=200,
            content=b"allowlisted-private-redirect",
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
        self.assertEqual(len(http_mock.calls), 2)

    @http_mock.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    def test_fetch_validated_url_skips_peer_validation_through_proxy(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=200,
            content=b"fetched-via-proxy",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_fetch_validated_url_allows_proxy_resolved_hostname(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "https://public.example.com/source",
            status_code=200,
            content=b"resolved-by-proxy",
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    @patch("weblate.utils.requests._get_response_peer_ip")
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_fetch_validated_url_allows_allowlisted_hostname_through_proxy(
        self, mocked_getaddrinfo, mocked_get_peer
    ) -> None:
        http_mock.register(
            "GET",
            "http://ollama/api/tags",
            status_code=200,
            content=b'{"models":[]}',
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
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    def test_fetch_validated_url_blocks_localhost_alias_through_proxy(self) -> None:
        http_mock.register(
            "GET",
            "http://localhost./source",
            status_code=200,
            content=b"should-not-be-fetched",
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

        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
    def test_fetch_validated_url_blocks_shorthand_loopback_through_proxy(self) -> None:
        http_mock.register(
            "GET",
            "http://127.1/source",
            status_code=200,
            content=b"should-not-be-fetched",
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

        self.assertEqual(len(http_mock.calls), 0)

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
