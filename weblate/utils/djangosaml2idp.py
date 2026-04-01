# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import zlib
from binascii import Error
from typing import TYPE_CHECKING
from xml.parsers.expat import ExpatError

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from djangosaml2idp.error_views import SamlIDPErrorView

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

LOGGER = logging.getLogger(__name__)


def is_incorrectly_signed(exception: Exception) -> bool:
    """Avoid importing pysaml2 during module import for optional/test environments."""
    return type(exception).__name__ == "IncorrectlySigned"


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
        if is_incorrectly_signed(exception) or isinstance(
            exception, (ValidationError, Error)
        ):
            return HttpResponseBadRequest(exception.args[0])

        return super().handle_error(request, exception, status_code, **kwargs)


@never_cache
@csrf_exempt
@require_http_methods(["GET", "POST"])
def sso_entry(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Wrap the upstream SSO entrypoint to normalize malformed requests."""
    from djangosaml2idp.views import sso_entry as djangosaml2idp_sso_entry

    return handle_sso_entry(request, djangosaml2idp_sso_entry, *args, **kwargs)


def handle_sso_entry(request: HttpRequest, entrypoint, *args, **kwargs) -> HttpResponse:
    """Normalize malformed SAML requests to a client error response."""
    try:
        return entrypoint(request, *args, **kwargs)
    except (UnicodeDecodeError, ExpatError, zlib.error, Error) as error:
        LOGGER.warning("Rejected malformed SAML request on %s: %s", request.path, error)
        return HttpResponseBadRequest("not a valid SAMLRequest")
