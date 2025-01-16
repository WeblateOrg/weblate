# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import requests
from django.core.cache import cache
from requests import Response

from weblate.logger import LOGGER
from weblate.utils.version import USER_AGENT


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    **kwargs,
) -> Response:
    agent = {"User-Agent": USER_AGENT}
    if headers is None:
        headers = agent
    else:
        headers.update(agent)
    response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    if raise_for_status:
        response.raise_for_status()
    return response


def get_uri_error(uri: str) -> str | None:
    """Return error for fetching the URL or None if it works."""
    if uri.startswith("https://nonexisting.weblate.org/"):
        return "Non existing test URL"
    cache_key = f"uri-check-{uri}"
    cached = cache.get(cache_key)
    if cached is True:
        LOGGER.debug("URL check for %s, cached success", uri)
        return None
    if cached:
        # The cache contains string here
        LOGGER.debug("URL check for %s, cached failure", uri)
        return cached
    try:
        with request("get", uri, stream=True):
            cache.set(cache_key, True, 12 * 3600)
            LOGGER.debug("URL check for %s, tested success", uri)
            return None
    except requests.exceptions.RequestException as error:
        if getattr(error.response, "status_code", 0) == 429:
            # Silently ignore rate limiting issues
            return None
        result = str(error)
        cache.set(cache_key, result, 3600)
        return result
