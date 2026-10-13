# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import base64
import logging
import string
import zlib
from binascii import Error
from typing import TYPE_CHECKING
from xml.parsers.expat import ExpatError

from defusedxml import minidom
from defusedxml.common import DefusedXmlException
from django.http import HttpResponseBadRequest
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

LOGGER = logging.getLogger(__name__)

MAX_SAML_REQUEST_SIZE = 64 * 1024
MAX_ENCODED_SAML_REQUEST_SIZE = 4 * ((MAX_SAML_REQUEST_SIZE + 2) // 3)
MAX_SAML_REQUEST_DEPTH = 64
BASE64_WHITESPACE = str.maketrans("", "", string.whitespace)


class SAMLRequestValidationError(ValueError):
    """SAML request violates the safe processing limits."""


def validate_saml_request(request: HttpRequest) -> None:
    """Validate SAML request encoding and size before upstream processing."""
    request_data = request.POST if request.method == "POST" else request.GET
    saml_request = request_data.get("SAMLRequest")
    if saml_request is None:
        return

    if len(saml_request) > MAX_ENCODED_SAML_REQUEST_SIZE:
        msg = "encoded SAML request is too large"
        raise SAMLRequestValidationError(msg)

    encoded = saml_request.translate(BASE64_WHITESPACE)
    decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    if len(decoded) > MAX_SAML_REQUEST_SIZE:
        msg = "decoded SAML request is too large"
        raise SAMLRequestValidationError(msg)

    if request.method == "POST":
        xml = decoded
    else:
        decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
        xml = decompressor.decompress(decoded, MAX_SAML_REQUEST_SIZE + 1)
        if len(xml) > MAX_SAML_REQUEST_SIZE or decompressor.unconsumed_tail:
            msg = "expanded SAML request is too large"
            raise SAMLRequestValidationError(msg)
        if not decompressor.eof or decompressor.unused_data:
            msg = "invalid compressed SAML request"
            raise SAMLRequestValidationError(msg)

    document = minidom.parseString(
        xml, forbid_dtd=True, forbid_entities=True, forbid_external=True
    )
    nodes = [(document, 0)]
    while nodes:
        node, depth = nodes.pop()
        if depth > MAX_SAML_REQUEST_DEPTH:
            msg = "SAML request is nested too deeply"
            raise SAMLRequestValidationError(msg)
        nodes.extend((child, depth + 1) for child in node.childNodes)
    document.unlink()


@never_cache
@csrf_exempt
@require_http_methods(["GET", "POST"])
def sso_entry(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Wrap the upstream SSO entrypoint to normalize malformed requests."""
    # ruff: ignore[import-outside-top-level]
    from djangosaml2idp.views import (
        sso_entry as djangosaml2idp_sso_entry,
    )

    return handle_sso_entry(request, djangosaml2idp_sso_entry, *args, **kwargs)


def handle_sso_entry(request: HttpRequest, entrypoint, *args, **kwargs) -> HttpResponse:
    """Normalize malformed SAML requests to a client error response."""
    try:
        validate_saml_request(request)
        return entrypoint(request, *args, **kwargs)
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        DefusedXmlException,
        ExpatError,
        SAMLRequestValidationError,
        zlib.error,
        Error,
    ) as error:
        LOGGER.warning("Rejected malformed SAML request on %s: %s", request.path, error)
        return HttpResponseBadRequest("not a valid SAMLRequest")
