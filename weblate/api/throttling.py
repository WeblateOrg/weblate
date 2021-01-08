#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from functools import wraps

from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle


def patch_throttle_request(func):
    """Stores throttling state in request to be picked up by ThrottlingMiddleware."""

    @wraps(func)
    def patched(self, request, view):
        result = func(self, request, view)
        if result and hasattr(self, "history"):
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
