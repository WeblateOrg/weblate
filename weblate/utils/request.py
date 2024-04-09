# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import user_agents


def get_request_meta(request, name: str) -> str:
    """Return request meta if request is set and meta available."""
    if not request:
        return ""
    return request.META.get(name, "")


def get_ip_address(request) -> str:
    """Return IP address for request."""
    return get_request_meta(request, "REMOTE_ADDR")


def get_user_agent_raw(request) -> str:
    """Return raw user agent string."""
    return get_request_meta(request, "HTTP_USER_AGENT")


def get_user_agent(request, max_length: int = 200) -> str:
    """Return formatted user agent for request."""
    raw = get_user_agent_raw(request)
    if not raw:
        return ""
    uaobj = user_agents.parse()
    return str(uaobj)[:max_length]
