# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http.request import HttpRequest


def get_request_meta(request: HttpRequest | None, name: str) -> str:
    """Return request meta if request is set and meta available."""
    if request is None:
        return ""
    return request.META.get(name, "")


def get_ip_address(request: HttpRequest | None) -> str:
    """Return IP address for request."""
    return get_request_meta(request, "REMOTE_ADDR")


def get_user_agent_raw(request: HttpRequest | None) -> str:
    """Return raw user agent string."""
    return get_request_meta(request, "HTTP_USER_AGENT")


def get_user_agent(request: HttpRequest | None, max_length: int = 200) -> str:
    """Return formatted user agent for request."""
    raw = get_user_agent_raw(request)
    if not raw:
        return ""

    # Lazily import as this is expensive
    import user_agents

    uaobj = user_agents.parse(raw)
    return str(uaobj)[:max_length]
