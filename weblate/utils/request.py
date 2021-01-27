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

import user_agents


def get_request_meta(request, name: str):
    """Returns request meta if request is set and meta available."""
    if not request:
        return ""
    return request.META.get(name, "")


def get_ip_address(request):
    """Return IP address for request."""
    return get_request_meta(request, "REMOTE_ADDR")


def get_user_agent_raw(request):
    """Return raw user agent string."""
    return get_request_meta(request, "HTTP_USER_AGENT")


def get_user_agent(request, max_length: int = 200):
    """Return formatted user agent for request."""
    uaobj = user_agents.parse(get_user_agent_raw(request))
    return str(uaobj)[:max_length]
