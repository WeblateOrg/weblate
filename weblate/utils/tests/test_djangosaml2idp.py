# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import sys
import zlib
from types import ModuleType
from typing import TYPE_CHECKING, Never
from unittest.mock import Mock, patch

import pytest
from django.http import HttpResponse
from django.test import (
    RequestFactory,
    SimpleTestCase,
    modify_settings,
    override_settings,
)
from django.urls import NoReverseMatch, Resolver404, include, path, resolve, reverse

from weblate.middleware import INLINE_PATHS
from weblate.utils.djangosaml2idp import WeblateSamlIDPErrorView
from weblate.utils.djangosaml2idp_views import (
    MAX_ENCODED_SAML_REQUEST_SIZE,
    MAX_SAML_REQUEST_DEPTH,
    MAX_SAML_REQUEST_SIZE,
    handle_sso_entry,
    sso_entry,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


class Djangosaml2idpTest(SimpleTestCase):
    @staticmethod
    def encode_request(xml: bytes, *, compressed: bool = False) -> str:
        if compressed:
            compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
            xml = compressor.compress(xml) + compressor.flush()
        return base64.b64encode(xml).decode()

    def test_error_view_can_be_imported(self) -> None:
        self.assertEqual(WeblateSamlIDPErrorView.__name__, "WeblateSamlIDPErrorView")

    def test_wrapped_sso_entry_is_in_inline_paths(self) -> None:
        self.assertIn("saml_login_binding", INLINE_PATHS)

    def test_sso_entry_is_csrf_exempt(self) -> None:
        self.assertTrue(getattr(sso_entry, "csrf_exempt", False))

    def test_handle_sso_entry_returns_bad_request_for_truncated_data(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/", {"SAMLRequest": self.encode_request(b"<request />")}
        )

        def entrypoint(_request: HttpRequest, *args: object, **kwargs: object) -> Never:
            msg = "Error -5 while decompressing data: incomplete or truncated stream"
            raise zlib.error(msg)

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "not a valid SAMLRequest")

    def test_handle_sso_entry_returns_bad_request_for_invalid_base64(self) -> None:
        request = RequestFactory().post("/idp/sso/post/", {"SAMLRequest": "ignored"})
        entrypoint = Mock(return_value=HttpResponse())
        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "not a valid SAMLRequest")
        entrypoint.assert_not_called()

    def test_handle_sso_entry_accepts_post_request(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/", {"SAMLRequest": self.encode_request(b"<request />")}
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 200)
        entrypoint.assert_called_once_with(request, binding="post")

    def test_handle_sso_entry_accepts_wrapped_post_request(self) -> None:
        encoded = self.encode_request(b"<request />")
        wrapped = f" {encoded[:8]}\r\n\t{encoded[8:]} "
        request = RequestFactory().post("/idp/sso/post/", {"SAMLRequest": wrapped})
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 200)
        entrypoint.assert_called_once_with(request, binding="post")

    def test_handle_sso_entry_accepts_redirect_request(self) -> None:
        request = RequestFactory().get(
            "/idp/sso/redirect/",
            {"SAMLRequest": self.encode_request(b"<request />", compressed=True)},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="redirect")

        self.assertEqual(response.status_code, 200)
        entrypoint.assert_called_once_with(request, binding="redirect")

    def test_handle_sso_entry_accepts_maximum_size_request(self) -> None:
        prefix = b"<request>"
        suffix = b"</request>"
        xml = (
            prefix + b"a" * (MAX_SAML_REQUEST_SIZE - len(prefix) - len(suffix)) + suffix
        )
        entrypoint = Mock(return_value=HttpResponse())

        for method, compressed in (("post", False), ("get", True)):
            with self.subTest(method=method):
                request = getattr(RequestFactory(), method)(
                    f"/idp/sso/{method}/",
                    {"SAMLRequest": self.encode_request(xml, compressed=compressed)},
                )

                response = handle_sso_entry(request, entrypoint, binding=method)

                self.assertEqual(response.status_code, 200)

        self.assertEqual(entrypoint.call_count, 2)

    def test_handle_sso_entry_rejects_compressed_bomb(self) -> None:
        xml = b"<request>" + b"<item />" * MAX_SAML_REQUEST_SIZE + b"</request>"
        request = RequestFactory().get(
            "/idp/sso/redirect/",
            {"SAMLRequest": self.encode_request(xml, compressed=True)},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="redirect")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_compressed_post_request(self) -> None:
        xml = b"<request>" + b"<item />" * MAX_SAML_REQUEST_SIZE + b"</request>"
        request = RequestFactory().post(
            "/idp/sso/post/",
            {"SAMLRequest": self.encode_request(xml, compressed=True)},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_oversized_encoded_request(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/",
            {"SAMLRequest": "A" * (MAX_ENCODED_SAML_REQUEST_SIZE + 1)},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_oversized_whitespace_request(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/",
            {"SAMLRequest": " " * MAX_ENCODED_SAML_REQUEST_SIZE + "AA=="},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_trailing_compressed_data(self) -> None:
        encoded = base64.b64decode(self.encode_request(b"<request />", compressed=True))
        request = RequestFactory().get(
            "/idp/sso/redirect/",
            {"SAMLRequest": base64.b64encode(encoded + b"trailing").decode()},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="redirect")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_truncated_compressed_data(self) -> None:
        encoded = base64.b64decode(self.encode_request(b"<request />", compressed=True))
        request = RequestFactory().get(
            "/idp/sso/redirect/",
            {"SAMLRequest": base64.b64encode(encoded[:-1]).decode()},
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="redirect")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_malformed_xml(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/", {"SAMLRequest": self.encode_request(b"<request>")}
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_document_type(self) -> None:
        request = RequestFactory().post(
            "/idp/sso/post/",
            {
                "SAMLRequest": self.encode_request(
                    b'<!DOCTYPE request [<!ENTITY value "test">]>'
                    b"<request>&value;</request>"
                )
            },
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_rejects_excessive_nesting(self) -> None:
        xml = b"<request>" * (MAX_SAML_REQUEST_DEPTH + 1) + b"</request>" * (
            MAX_SAML_REQUEST_DEPTH + 1
        )
        request = RequestFactory().post(
            "/idp/sso/post/", {"SAMLRequest": self.encode_request(xml)}
        )
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        entrypoint.assert_not_called()

    def test_handle_sso_entry_delegates_missing_request(self) -> None:
        request = RequestFactory().get("/idp/sso/redirect/")
        entrypoint = Mock(return_value=HttpResponse())

        response = handle_sso_entry(request, entrypoint, binding="redirect")

        self.assertEqual(response.status_code, 200)
        entrypoint.assert_called_once_with(request, binding="redirect")


@pytest.mark.filterwarnings(
    "ignore:CFB has been moved:cryptography.utils.CryptographyDeprecationWarning"
)
@modify_settings(INSTALLED_APPS={"append": "djangosaml2idp"})
class Djangosaml2idpURLTest(SimpleTestCase):
    def setUp(self) -> None:
        urlconf = ModuleType("djangosaml2idp_test_urls")
        urlconf.__dict__["urlpatterns"] = [
            path(
                "idp/sso/<str:binding>/",
                sso_entry,
                name="saml_login_binding",
            ),
            path("idp/", include("weblate.utils.djangosaml2idp_urls")),
        ]
        self.enterContext(patch.dict(sys.modules, {urlconf.__name__: urlconf}))
        self.enterContext(override_settings(ROOT_URLCONF=urlconf.__name__))

    def test_slo_is_not_available(self) -> None:
        for binding in ("redirect", "post"):
            with self.subTest(binding=binding), self.assertRaises(Resolver404):
                resolve(f"/idp/slo/{binding}/")

        with self.assertRaises(NoReverseMatch):
            reverse(
                "djangosaml2idp:saml_logout_binding",
                kwargs={"binding": "redirect"},
            )

    def test_sso_uses_guarded_view(self) -> None:
        expected_url = "/idp/sso/redirect/"
        self.assertEqual(
            reverse("saml_login_binding", kwargs={"binding": "redirect"}),
            expected_url,
        )
        self.assertEqual(
            reverse(
                "djangosaml2idp:saml_login_binding",
                kwargs={"binding": "redirect"},
            ),
            expected_url,
        )
        self.assertIs(resolve(expected_url).func, sso_entry)

    def test_remaining_routes_are_available(self) -> None:
        expected_urls = {
            "saml_idp_init": "/idp/sso/init/",
            "saml_login_process": "/idp/login/process/",
            "saml_multi_factor": "/idp/login/process_multi_factor/",
            "saml2_idp_metadata": "/idp/metadata/",
        }

        for name, expected_url in expected_urls.items():
            with self.subTest(name=name):
                self.assertEqual(
                    reverse(f"djangosaml2idp:{name}"),
                    expected_url,
                )
