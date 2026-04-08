# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import zlib
from binascii import Error

from django.test import RequestFactory, SimpleTestCase

from weblate.middleware import INLINE_PATHS
from weblate.utils.djangosaml2idp import WeblateSamlIDPErrorView
from weblate.utils.djangosaml2idp_views import handle_sso_entry, sso_entry


class Djangosaml2idpTest(SimpleTestCase):
    def test_error_view_can_be_imported(self) -> None:
        self.assertEqual(WeblateSamlIDPErrorView.__name__, "WeblateSamlIDPErrorView")

    def test_wrapped_sso_entry_is_in_inline_paths(self) -> None:
        self.assertIn("saml_login_binding", INLINE_PATHS)

    def test_sso_entry_is_csrf_exempt(self) -> None:
        self.assertTrue(getattr(sso_entry, "csrf_exempt", False))

    def test_handle_sso_entry_returns_bad_request_for_truncated_data(self) -> None:
        request = RequestFactory().post("/idp/sso/post/", {"SAMLRequest": "ignored"})

        def entrypoint(_request, *args, **kwargs):
            msg = "Error -5 while decompressing data: incomplete or truncated stream"
            raise zlib.error(msg)

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "not a valid SAMLRequest")

    def test_handle_sso_entry_returns_bad_request_for_invalid_base64(self) -> None:
        request = RequestFactory().post("/idp/sso/post/", {"SAMLRequest": "ignored"})

        def entrypoint(_request, *args, **kwargs):
            msg = "Incorrect padding"
            raise Error(msg)

        response = handle_sso_entry(request, entrypoint, binding="post")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "not a valid SAMLRequest")
