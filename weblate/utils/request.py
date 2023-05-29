# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
