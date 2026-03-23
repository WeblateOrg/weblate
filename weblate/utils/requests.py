# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import requests
from django.core.cache import cache

from weblate.logger import LOGGER
from weblate.utils.validators import validate_asset_url
from weblate.utils.version import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Generator

    from requests import Response


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    **kwargs,
) -> Response:
    agent = {"User-Agent": USER_AGENT}
    headers = {**headers, **agent} if headers is not None else agent
    response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    if raise_for_status:
        response.raise_for_status()
    return response


@contextmanager
def asset_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    max_redirects: int = 5,
    **kwargs,
) -> Generator[Response, None, None]:
    """Fetch an asset while validating each redirect target before following it."""
    history: list[Response] = []
    current_url = url
    current_method = method
    request_kwargs = kwargs.copy()
    request_kwargs["allow_redirects"] = False

    agent = {"User-Agent": USER_AGENT}
    request_headers = {**headers, **agent} if headers is not None else agent

    with requests.Session() as session:
        for _ in range(max_redirects + 1):
            validate_asset_url(current_url)
            response = session.request(
                current_method,
                current_url,
                headers=request_headers,
                timeout=timeout,
                **request_kwargs,
            )
            response.history = history.copy()
            if not response.is_redirect:
                try:
                    if raise_for_status:
                        response.raise_for_status()
                    with response:
                        yield response
                finally:
                    response.close()
                return

            try:
                next_url = urljoin(response.url, response.headers["location"])
                validate_asset_url(next_url)
                session.cookies.update(response.cookies)
                history.append(response)
            finally:
                response.close()
            current_url = next_url

            if (
                response.status_code in {301, 302, 303}
                and current_method.upper() != "HEAD"
            ):
                current_method = "GET"
                request_kwargs.pop("data", None)
                request_kwargs.pop("json", None)
                request_kwargs.pop("files", None)

    msg = f"Exceeded {max_redirects} redirects."
    raise requests.TooManyRedirects(msg)


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
        with http_request("get", uri, stream=True):
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
