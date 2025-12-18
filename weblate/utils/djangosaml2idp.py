# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import HttpResponseBadRequest
from djangosaml2idp.error_views import SamlIDPErrorView

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
        if isinstance(exception, KeyError) and exception.args[0] == "SAMLRequest":
            # Silently ignore this as it is caused by bad invocation
            return HttpResponseBadRequest("Missing SAMLRequest in session")
        return super().handle_error(request, exception, status_code, **kwargs)
