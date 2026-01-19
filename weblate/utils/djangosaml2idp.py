# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from binascii import Error
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from djangosaml2idp.error_views import SamlIDPErrorView
from saml2.response import IncorrectlySigned

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class WeblateSamlIDPErrorView(SamlIDPErrorView):
    @classmethod
    def handle_error(
        cls,
        request: HttpRequest,
        exception: Exception,
        status_code: int = 500,
        **kwargs,
    ) -> HttpResponse:
        # Avoid raising HTTP 500 for client errors

        # missing parameter
        if isinstance(exception, KeyError) and exception.args[0] == "SAMLRequest":
            return HttpResponseBadRequest("Missing SAMLRequest in session")

        # wrong signature, missing parameter, or invalid base64 string
        if isinstance(exception, (IncorrectlySigned, ValidationError, Error)):
            return HttpResponseBadRequest(exception.args[0])

        return super().handle_error(request, exception, status_code, **kwargs)
