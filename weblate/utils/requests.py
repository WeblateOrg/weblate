# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import requests
from django.core.cache import cache
from requests import Response
from requests.utils import select_proxy

from weblate.logger import LOGGER
from weblate.utils.outbound import (
    validate_outbound_url,
    validate_runtime_ip,
    validate_runtime_url,
)
from weblate.utils.validators import validate_asset_url
from weblate.utils.version import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Generator


RequestValidator = Callable[[str], None]
ResponseValidator = Callable[[Response, bool], None]


def _prepare_headers(headers: dict[str, str] | None) -> dict[str, str]:
    agent = {"User-Agent": USER_AGENT}
    return {**headers, **agent} if headers is not None else agent


def validate_request_url(
    url: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    with requests.Session() as session:
        request_settings = session.merge_environment_settings(
            url,
            {},
            False,
            None,
            None,
        )
    used_proxy = select_proxy(url, request_settings["proxies"]) is not None
    if used_proxy:
        validate_outbound_url(
            url,
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        )
        return

    validate_runtime_url(url, allow_private_targets=allow_private_targets)


def _strip_redirect_auth(
    session: requests.Session,
    request_headers: dict[str, str],
    request_kwargs: dict,
    current_url: str,
    next_url: str,
) -> None:
    if not session.should_strip_auth(current_url, next_url):
        return

    request_headers.pop("Authorization", None)
    request_headers.pop("Proxy-Authorization", None)
    request_kwargs.pop("auth", None)


def _should_redirect_to_get(status_code: int, method: str) -> bool:
    normalized_method = method.upper()
    if normalized_method == "HEAD":
        return False
    if status_code == 303:
        return True
    if status_code == 302:
        return True
    return status_code == 301 and normalized_method == "POST"


def _request_with_redirects(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    allow_redirects: bool = True,
    stream: bool = False,
    max_redirects: int = 5,
    validate_url: RequestValidator | None = None,
    validate_proxied_url: RequestValidator | None = None,
    validate_response: ResponseValidator | None = None,
    **kwargs,
) -> Response:
    request_kwargs = kwargs.copy()
    request_kwargs["allow_redirects"] = False
    history: list[Response] = []
    current_url = url
    current_method = method
    request_headers = _prepare_headers(headers)

    with requests.Session() as session:
        for _ in range(max_redirects + 1):
            request_settings = session.merge_environment_settings(
                current_url,
                request_kwargs.get("proxies") or {},
                stream,
                request_kwargs.get("verify"),
                request_kwargs.get("cert"),
            )
            used_proxy = (
                select_proxy(current_url, request_settings["proxies"]) is not None
            )
            if validate_url is not None:
                validator = (
                    validate_proxied_url
                    if used_proxy and validate_proxied_url is not None
                    else validate_url
                )
                validator(current_url)
            response = session.request(
                current_method,
                current_url,
                headers=request_headers,
                timeout=timeout,
                stream=stream,
                **request_kwargs,
            )
            response.history = history.copy()
            if validate_response is not None:
                try:
                    validate_response(response, used_proxy)
                except Exception:
                    response.close()
                    raise

            if not allow_redirects or not response.is_redirect:
                return response

            try:
                next_url = urljoin(response.url, response.headers["location"])
                _strip_redirect_auth(
                    session, request_headers, request_kwargs, current_url, next_url
                )
                session.cookies.update(response.cookies)
                history.append(response)
            except Exception:
                response.close()
                raise

            current_url = next_url

            if _should_redirect_to_get(response.status_code, current_method):
                current_method = "GET"
                request_kwargs.pop("data", None)
                request_kwargs.pop("json", None)
                request_kwargs.pop("files", None)

            response.close()

    msg = f"Exceeded {max_redirects} redirects."
    raise requests.TooManyRedirects(msg)


def _get_response_peer_ip(response: Response) -> str | None:
    try:
        connection = getattr(response.raw, "connection", None)
        if connection is None or connection.sock is None:
            return None
        peer = connection.sock.getpeername()
    except (AttributeError, OSError):
        return None

    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return None


def _validate_response_peer(
    response: Response, *, allow_private_targets: bool, used_proxy: bool = False
) -> None:
    if allow_private_targets:
        return
    if used_proxy:
        return

    if (peer_ip := _get_response_peer_ip(response)) is None:
        LOGGER.warning(
            "Skipping peer IP validation for direct request to %s because the "
            "connected peer address could not be determined.",
            response.url,
        )
        return

    validate_runtime_ip(peer_ip, allow_private_targets=allow_private_targets)


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    allow_redirects: bool = True,
    stream: bool = False,
    validate_url: bool = False,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    max_redirects: int = 5,
    **kwargs,
) -> Response:
    if validate_url and stream:
        msg = "Streaming requests are not supported with URL validation enabled."
        raise ValueError(msg)

    if not validate_url:
        response = requests.request(
            method,
            url,
            headers=_prepare_headers(headers),
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
            **kwargs,
        )
        if raise_for_status:
            response.raise_for_status()
        return response

    response = _request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        # Keep response socket open so peer IP can be validated per request.
        stream=True,
        max_redirects=max_redirects,
        validate_url=lambda request_url: validate_runtime_url(
            request_url, allow_private_targets=allow_private_targets
        ),
        validate_proxied_url=lambda request_url: validate_outbound_url(
            request_url,
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        ),
        validate_response=lambda response, used_proxy: _validate_response_peer(
            response,
            allow_private_targets=allow_private_targets,
            used_proxy=used_proxy,
        ),
        **kwargs,
    )
    try:
        if raise_for_status:
            response.raise_for_status()
        # Preserve non-streaming behavior for callers by eagerly consuming body.
        _ = response.content
    finally:
        response.close()
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
    stream = kwargs.pop("stream", False)
    response = _request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        stream=stream,
        max_redirects=max_redirects,
        validate_url=validate_asset_url,
        **kwargs,
    )
    try:
        if raise_for_status:
            response.raise_for_status()
        with response:
            yield response
    finally:
        response.close()


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
        with http_request("get", uri, stream=True, allow_redirects=True):
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
