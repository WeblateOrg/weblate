# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import responses
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.requests import asset_request, get_uri_error


class AssetRequestTest(SimpleTestCase):
    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_asset_request_follows_allowed_redirect(self) -> None:
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

        with asset_request(
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
    def test_asset_request_blocks_disallowed_redirect(self) -> None:
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
            asset_request("get", "https://images.allowed.com/redirect-image.png"),
        ):
            pass

        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://images.allowed.com/redirect-image.png",
        )

    @responses.activate
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_asset_request_preserves_redirect_cookies(self) -> None:
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

        with asset_request(
            "get", "https://images.allowed.com/redirect-image.png"
        ) as response:
            self.assertEqual(response.content, b"image-data")

        self.assertEqual(
            responses.calls[1].request.headers["Cookie"],
            "asset-token=allowed",
        )


class GetUriErrorTest(SimpleTestCase):
    @responses.activate
    def test_get_uri_error_does_not_follow_redirects(self) -> None:
        responses.add(
            responses.GET,
            "https://example.com/source",
            status=302,
            headers={"Location": "https://internal.example.test/final"},
        )
        responses.add(
            responses.GET,
            "https://internal.example.test/final",
            status=200,
            body=b"should-not-be-fetched",
        )

        self.assertEqual(
            get_uri_error("https://example.com/source"),
            "URL redirects with HTTP 302 to https://internal.example.test/final.",
        )
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://example.com/source",
        )
