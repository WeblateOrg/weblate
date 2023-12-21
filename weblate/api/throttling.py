# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps

from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle


def patch_throttle_request(func):
    """Stores throttling state in request to be picked up by ThrottlingMiddleware."""

    @wraps(func)
    def patched(self, request, view):
        result = func(self, request, view)
        if hasattr(self, "history"):
            request.META["throttling_state"] = self
        return result

    return patched


class AnonRateThrottle(DRFAnonRateThrottle):
    @patch_throttle_request
    def allow_request(self, request, view):
        return super().allow_request(request, view)


class UserRateThrottle(DRFUserRateThrottle):
    @patch_throttle_request
    def allow_request(self, request, view):
        return super().allow_request(request, view)
