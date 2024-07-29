# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def patch_throttle_request(func):
    """Store throttling state in request to be picked up by ThrottlingMiddleware."""

    @wraps(func)
    def patched(self, request: AuthenticatedHttpRequest, view):
        result = func(self, request, view)
        if hasattr(self, "history"):
            request.META["throttling_state"] = self
        return result

    return patched


class AnonRateThrottle(DRFAnonRateThrottle):
    @patch_throttle_request
    def allow_request(self, request: AuthenticatedHttpRequest, view):
        return super().allow_request(request, view)


class UserRateThrottle(DRFUserRateThrottle):
    @patch_throttle_request
    def allow_request(self, request: AuthenticatedHttpRequest, view):
        return super().allow_request(request, view)
