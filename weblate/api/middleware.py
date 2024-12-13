# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from django.conf import settings
from django.http.request import UnreadablePostError

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATELIMIT_RESET_HEADER = "X-RateLimit-Reset"


class ThrottlingMiddleware:
    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    def __call__(self, request: AuthenticatedHttpRequest):
        response = self.get_response(request)

        # API payload workaround
        if request.method != "GET" and request.path_info.startswith(
            f"{settings.URL_PREFIX}/api"
        ):
            # Make sure full request is read. Django REST Framework lazily loads
            # request body when needed, but keeping the payload in the stream the client
            # ends up with an error:
            #
            # - HTTP/1.1: transfer closed with outstanding read data remaining
            # - HTTP/2: stream was not closed cleanly
            with contextlib.suppress(UnreadablePostError):
                request.read()

        # Actual throttling
        throttling = request.META.get("throttling_state", None)
        if throttling is not None:
            response[RATELIMIT_LIMIT_HEADER] = throttling.num_requests
            response[RATELIMIT_REMAINING_HEADER] = throttling.num_requests - len(
                throttling.history
            )
            if throttling.history:
                remaining_duration = throttling.duration - (
                    throttling.now - throttling.history[-1]
                )
            else:
                remaining_duration = throttling.duration
            response[RATELIMIT_RESET_HEADER] = int(remaining_duration)
        return response
