# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from unittest.mock import Mock, patch

import responses
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings
from requests.cookies import RequestsCookieJar

from weblate.utils.requests import (
    _validate_response_peer,
    fetch_validated_url,
    get_uri_error,
    open_asset_url,
)


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


class GetUriErrorTest(SimpleTestCase):
    @responses.activate
    def test_get_uri_error_allows_internal_host_by_default(self) -> None:
        responses.add(
            responses.GET,
            "https://gitlab.intranet.example/project",
            status=200,
            body=b"ok",
        )

        self.assertIsNone(get_uri_error("https://gitlab.intranet.example/project"))

    @patch("weblate.utils.requests._probe_validated_url")
    def test_get_uri_error_flattens_validation_error(self, mocked_probe) -> None:
        mocked_probe.side_effect = ValidationError("This URL is prohibited")

        self.assertEqual(
            get_uri_error("https://example.com/source"),
            "This URL is prohibited",
        )


class FetchValidatedURLTest(SimpleTestCase):
    def test_fetch_validated_url_strips_auth_on_cross_origin_redirect(self) -> None:
        recorded_calls: list[tuple[dict[str, str], bool]] = []
        redirect_response = Mock()
        redirect_response.is_redirect = True
        redirect_response.url = "https://public.example.com/source"
        redirect_response.headers = {"location": "https://other.example.com/final"}
        redirect_response.cookies = RequestsCookieJar()
        redirect_response.history = []
        redirect_response.close = Mock()

        final_response = Mock()
        final_response.is_redirect = False
        final_response.url = "https://other.example.com/final"
        final_response.headers = {}
        final_response.history = []
        final_response.raise_for_status = Mock()
        final_response.content = b"ok"

        with patch("requests.sessions.Session.request") as mocked_request:

            def record_request(*args, **kwargs):
                recorded_calls.append((dict(kwargs["headers"]), "auth" in kwargs))
                if len(recorded_calls) == 1:
                    return redirect_response
                return final_response

            mocked_request.side_effect = record_request

            fetch_validated_url(
                "get",
                "https://public.example.com/source",
                headers={"Authorization": "Bearer secret"},
                auth=("user", "pass"),
                allow_redirects=True,
            )

        self.assertEqual(mocked_request.call_count, 2)
        self.assertEqual(recorded_calls[0][0]["Authorization"], "Bearer secret")
        self.assertNotIn("Authorization", recorded_calls[1][0])
        self.assertFalse(recorded_calls[1][1])

    def test_fetch_validated_url_preserves_delete_method_on_301_redirect(self) -> None:
        recorded_calls: list[tuple[str, dict[str, object]]] = []
        redirect_response = Mock()
        redirect_response.is_redirect = True
        redirect_response.status_code = 301
        redirect_response.url = "https://public.example.com/source"
        redirect_response.headers = {"location": "https://public.example.com/final"}
        redirect_response.cookies = RequestsCookieJar()
        redirect_response.history = []
        redirect_response.close = Mock()

        final_response = Mock()
        final_response.is_redirect = False
        final_response.url = "https://public.example.com/final"
        final_response.headers = {}
        final_response.history = []
        final_response.raise_for_status = Mock()
        final_response.content = b"ok"

        with patch("requests.sessions.Session.request") as mocked_request:

            def record_request(*args, **kwargs):
                recorded_calls.append((args[0], dict(kwargs)))
                if len(recorded_calls) == 1:
                    return redirect_response
                return final_response

            mocked_request.side_effect = record_request

            fetch_validated_url(
                "delete",
                "https://public.example.com/source",
                allow_redirects=True,
                data=b"payload",
            )

        self.assertEqual(mocked_request.call_count, 2)
        self.assertEqual(recorded_calls[0][0], "delete")
        self.assertEqual(recorded_calls[1][0], "delete")
        self.assertEqual(recorded_calls[1][1]["data"], b"payload")

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

    @patch("weblate.utils.requests.LOGGER.warning")
    @patch("weblate.utils.requests._get_response_peer_ip", return_value=None)
    def test_http_request_logs_when_peer_ip_is_unavailable(
        self, mocked_get_peer, mocked_warning
    ) -> None:
        response = Mock()
        response.url = "https://public.example.com/source"

        _validate_response_peer(
            response,
            allow_private_targets=False,
            used_proxy=False,
        )

        mocked_get_peer.assert_called_once_with(response)
        mocked_warning.assert_called_once_with(
            "Skipping peer IP validation for direct request to %s because the "
            "connected peer address could not be determined.",
            "https://public.example.com/source",
        )

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
