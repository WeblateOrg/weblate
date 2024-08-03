# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class ThrottlingMiddleware:
    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    def __call__(self, request: AuthenticatedHttpRequest):
        response = self.get_response(request)
        throttling = request.META.get("throttling_state", None)
        if throttling is not None:
            response["X-RateLimit-Limit"] = throttling.num_requests
            response["X-RateLimit-Remaining"] = throttling.num_requests - len(
                throttling.history
            )
            if throttling.history:
                remaining_duration = throttling.duration - (
                    throttling.now - throttling.history[-1]
                )
            else:
                remaining_duration = throttling.duration
            response["X-RateLimit-Reset"] = int(remaining_duration)
        return response
