# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from contextlib import contextmanager
from threading import get_ident
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx2
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils import tracing
from weblate.utils.requests import (
    PEER_IP_RESPONSE_ATTR,
    AsyncHTTPClient,
    HTTPClient,
    _get_proxy,
    _get_response_peer_ip,
    _validate_response_peer,
    fetch_url,
    fetch_validated_url,
    get_uri_error,
    open_asset_url,
    open_restricted_asset_url,
    trace_http_request,
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


class FetchURLTest(SimpleTestCase):
    @patch(
        "weblate.utils.requests.getproxies",
        return_value={
            "https": "http://proxy.example:8080",
            "no": "example.com:8443",
        },
    )
    @patch("weblate.utils.requests.proxy_bypass", return_value=False)
    def test_get_proxy_honors_no_proxy_port(
        self, mocked_proxy_bypass, mocked_getproxies
    ) -> None:
        self.assertIsNone(_get_proxy("https://example.com:8443/source"))
        self.assertEqual(
            _get_proxy("https://example.com:443/source"),
            "http://proxy.example:8080",
        )

    @patch(
        "weblate.utils.requests.getproxies",
        return_value={
            "https": "http://proxy.example:8080",
            "no": "10.0.0.0/8",
        },
    )
    @patch("weblate.utils.requests.proxy_bypass", return_value=False)
    def test_get_proxy_honors_no_proxy_cidr(
        self, mocked_proxy_bypass, mocked_getproxies
    ) -> None:
        self.assertIsNone(_get_proxy("https://10.1.2.3/source"))
        self.assertEqual(
            _get_proxy("https://192.0.2.1/source"),
            "http://proxy.example:8080",
        )

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

    def test_http_client_buffers_response_inside_span(self) -> None:
        events: list[str] = []
        request = httpx2.Request("GET", "https://example.com/data")
        response = httpx2.Response(
            200,
            request=request,
            stream=TrackedSyncStream(events),
        )
        transport_client = MagicMock()
        transport_client.build_request.return_value = request
        transport_client.send.return_value = response

        @contextmanager
        def tracked_span(_request):
            events.append("span-start")
            try:
                yield None
            finally:
                events.append("span-end")

        client = HTTPClient()
        with (
            patch.object(
                client,
                "_get_client",
                return_value=(transport_client, False),
            ),
            patch(
                "weblate.utils.requests.trace_http_request",
                side_effect=tracked_span,
            ),
        ):
            result = client.request("get", "https://example.com/data")

        self.assertEqual(result.content, b"response-body")
        self.assertEqual(events, ["span-start", "read", "span-end"])

    def test_async_http_client_buffers_response_inside_span(self) -> None:
        events: list[str] = []
        request = httpx2.Request("GET", "https://example.com/data")
        response = httpx2.Response(
            200,
            request=request,
            stream=TrackedAsyncStream(events),
        )
        transport_client = MagicMock()
        transport_client.build_request.return_value = request
        transport_client.send = AsyncMock(return_value=response)

        @contextmanager
        def tracked_span(_request):
            events.append("span-start")
            try:
                yield None
            finally:
                events.append("span-end")

        client = AsyncHTTPClient()
        with (
            patch.object(
                client,
                "_get_client",
                return_value=(transport_client, False),
            ),
            patch(
                "weblate.utils.requests.trace_http_request",
                side_effect=tracked_span,
            ),
        ):
            result = async_to_sync(client.request)("get", "https://example.com/data")

        self.assertEqual(result.content, b"response-body")
        self.assertEqual(events, ["span-start", "read", "span-end"])

    def test_async_http_client_validates_request_off_event_loop(self) -> None:
        request = httpx2.Request("GET", "https://example.com/data")
        response = httpx2.Response(
            200,
            request=request,
            content=b"response-body",
        )
        transport_client = MagicMock()
        transport_client.build_request.return_value = request
        transport_client.send = AsyncMock(return_value=response)
        validation_thread_ids: list[int] = []
        validators = MagicMock()

        def record_validation_thread(*_args, **_kwargs) -> None:
            validation_thread_ids.append(get_ident())

        validators.validate_request_url.side_effect = record_validation_thread
        client = AsyncHTTPClient()

        async def make_request() -> tuple[int, httpx2.Response]:
            event_loop_thread_id = get_ident()
            result = await client.request(
                "get",
                "https://example.com/data",
                validators=validators,
            )
            return event_loop_thread_id, result

        with patch.object(
            client,
            "_get_client",
            return_value=(transport_client, False),
        ):
            event_loop_thread_id, result = async_to_sync(make_request)()

        self.assertEqual(result.content, b"response-body")
        self.assertEqual(len(validation_thread_ids), 1)
        self.assertNotEqual(validation_thread_ids[0], event_loop_thread_id)
        validators.validate_request_url.assert_called_once_with(
            "https://example.com/data",
            used_proxy=False,
        )

    def test_http_trace_uses_configured_tracer(self) -> None:
        request = httpx2.Request("GET", "https://example.com/data")
        span = MagicMock()
        span_context = MagicMock()
        span_context.__enter__.return_value = span
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = span_context
        tracing.configure_opentelemetry_tracer(tracer)
        self.addCleanup(tracing.configure_opentelemetry_tracer, None)

        with trace_http_request(request) as current_span:
            self.assertIs(current_span, span)

        tracer.start_as_current_span.assert_called_once()


class OpenAssetURLTest(SimpleTestCase):
    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_asset_url_follows_allowed_redirect(self) -> None:
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

        with open_asset_url(
            "get", "https://images.allowed.com/redirect-image.png"
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(
            responses.calls[1].request.url,
            "https://cdn.allowed.com/final-image.png",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_asset_url_blocks_disallowed_redirect(self) -> None:
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
            open_asset_url("get", "https://images.allowed.com/redirect-image.png"),
        ):
            pass

        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://images.allowed.com/redirect-image.png",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_asset_url_preserves_redirect_cookies(self) -> None:
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

        with open_asset_url(
            "get", "https://images.allowed.com/redirect-image.png"
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(
            responses.calls[1].request.headers["Cookie"],
            "asset-token=allowed",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_asset_url_raises_validation_error_for_http_status(self) -> None:
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
            open_asset_url("get", "https://images.allowed.com/missing-image.png"),
        ):
            pass

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_open_asset_url_raises_validation_error_for_redirect_status(self) -> None:
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
            open_asset_url("get", "https://images.allowed.com/redirect-image.png"),
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
                allow_private_targets=False,
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
            allowed_domains=["private.example.com"],
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
    def test_fetch_validated_url_blocks_private_target(
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
                allow_private_targets=False,
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
            allowed_domains=["private.example"],
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
            allowed_domains=["private.example"],
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
                allowed_domains=["ollama"],
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
            allowed_domains=["private.example"],
            used_proxy=False,
        )

        mocked_get_peer.assert_not_called()
