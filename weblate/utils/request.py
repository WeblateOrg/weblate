# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.conf import settings
from django.utils.encoding import force_text

import user_agents


def get_ip_address(request):
    """Return IP address for request."""
    if settings.IP_BEHIND_REVERSE_PROXY:
        proxy = request.META.get(settings.IP_PROXY_HEADER)
    else:
        proxy = None
    if proxy:
        # X_FORWARDED_FOR returns client1, proxy1, proxy2,...
        return proxy.split(', ')[settings.IP_PROXY_OFFSET]
    return request.META.get('REMOTE_ADDR', '')


def get_user_agent(request, max_length=200):
    """Return user agent for request."""
    uaobj = user_agents.parse(
        force_text(
            request.META.get('HTTP_USER_AGENT', ''),
            errors='replace'
        )
    )
    return force_text(uaobj)[:max_length]
