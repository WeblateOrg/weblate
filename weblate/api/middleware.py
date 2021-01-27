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


class ThrottlingMiddleware:
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "throttling_state" in request.META:
            throttling = request.META["throttling_state"]
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
