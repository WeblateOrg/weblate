# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import zlib
from binascii import Error
from typing import TYPE_CHECKING
from xml.parsers.expat import ExpatError

from django.http import HttpResponseBadRequest
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

LOGGER = logging.getLogger(__name__)


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
