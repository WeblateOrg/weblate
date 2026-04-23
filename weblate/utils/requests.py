# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from requests.utils import select_proxy

from weblate.logger import LOGGER
from weblate.utils.outbound import (
    is_allowlisted_hostname,
    validate_outbound_url,
    validate_runtime_ip,
    validate_runtime_url,
)
from weblate.utils.validators import validate_asset_url
from weblate.utils.version import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from requests import Response


@dataclass(slots=True)
class RedirectValidators:
    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        return

    def validate_response(self, response: Response, *, used_proxy: bool) -> None:
        return


@dataclass(slots=True)
class RuntimeRedirectValidators(RedirectValidators):
    allow_private_targets: bool = True
    allowed_domains: list[str] | tuple[str, ...] = ()

    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        hostname = urlparse(request_url).hostname or ""
        if is_allowlisted_hostname(hostname, self.allowed_domains):
            validate_outbound_url(
                request_url,
                allow_private_targets=False,
                allowed_domains=self.allowed_domains,
            )
            return
        if used_proxy:
            validate_outbound_url(
                request_url,
                allow_private_targets=self.allow_private_targets,
                allowed_domains=self.allowed_domains,
            )
            return
        validate_runtime_url(
            request_url, allow_private_targets=self.allow_private_targets
        )

    def validate_response(self, response: Response, *, used_proxy: bool) -> None:
        _validate_response_peer(
            response,
            allow_private_targets=self.allow_private_targets,
            allowed_domains=self.allowed_domains,
            used_proxy=used_proxy,
        )


@dataclass(slots=True)
class AssetRedirectValidators(RedirectValidators):
    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        validate_asset_url(request_url)


@dataclass(slots=True)
class ChainedRedirectValidators(RedirectValidators):
    request_validators: tuple[Callable[[str], None], ...] = ()
    response_validator: Callable[[Response, bool], None] | None = None

    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        for validator in self.request_validators:
            validator(request_url)

    def validate_response(self, response: Response, *, used_proxy: bool) -> None:
        if self.response_validator is None:
            return
        self.response_validator(response, used_proxy)


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
        used_proxy = _request_uses_proxy(
            session,
            url,
            stream=False,
        )
    if used_proxy:
        validate_outbound_url(
            url,
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        )
        return

    validate_runtime_url(url, allow_private_targets=allow_private_targets)


def _request_uses_proxy(
    session: requests.Session,
    url: str,
    *,
    stream: bool,
    request_kwargs: dict | None = None,
) -> bool:
    request_kwargs = request_kwargs or {}
    request_settings = session.merge_environment_settings(
        url,
        request_kwargs.get("proxies") or {},
        stream,
        request_kwargs.get("verify"),
        request_kwargs.get("cert"),
    )
    return select_proxy(url, request_settings["proxies"]) is not None


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
    validators: RedirectValidators | None = None,
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
            used_proxy = _request_uses_proxy(
                session,
                current_url,
                stream=stream,
                request_kwargs=request_kwargs,
            )
            if validators is not None:
                validators.validate_request_url(current_url, used_proxy=used_proxy)
            response = session.request(
                current_method,
                current_url,
                headers=request_headers,
                timeout=timeout,
                stream=stream,
                **request_kwargs,
            )
            response.history = history.copy()
            if validators is not None:
                try:
                    validators.validate_response(response, used_proxy=used_proxy)
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
    response: Response,
    *,
    allow_private_targets: bool,
    allowed_domains: list[str] | tuple[str, ...] = (),
    used_proxy: bool = False,
) -> None:
    if allow_private_targets:
        return
    if used_proxy:
        return
    hostname = urlparse(response.url).hostname or ""
    if is_allowlisted_hostname(hostname, allowed_domains):
        return

    if (peer_ip := _get_response_peer_ip(response)) is None:
        LOGGER.warning(
            "Skipping peer IP validation for direct request to %s because the "
            "connected peer address could not be determined.",
            response.url,
        )
        return

    validate_runtime_ip(peer_ip, allow_private_targets=allow_private_targets)


def _validated_request_with_redirects(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    allow_redirects: bool = True,
    stream: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    max_redirects: int = 5,
    **kwargs,
) -> Response:
    return _request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        # Keep response socket open so peer IP can be validated per request.
        stream=stream,
        max_redirects=max_redirects,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        ),
        **kwargs,
    )


def _asset_request_with_redirects(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    stream: bool = False,
    max_redirects: int = 5,
    **kwargs,
) -> Response:
    return _request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        stream=stream,
        allow_redirects=True,
        max_redirects=max_redirects,
        validators=AssetRedirectValidators(),
        **kwargs,
    )


def _buffer_response(response: Response, *, raise_for_status: bool) -> Response:
    try:
        if raise_for_status:
            response.raise_for_status()
        _ = response.content
    finally:
        response.close()
    return response


def fetch_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    allow_redirects: bool = True,
    **kwargs,
) -> Response:
    response = requests.request(
        method,
        url,
        headers=_prepare_headers(headers),
        timeout=timeout,
        allow_redirects=allow_redirects,
        stream=False,
        **kwargs,
    )
    if raise_for_status:
        response.raise_for_status()
    return response


def fetch_validated_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    allow_redirects: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    max_redirects: int = 5,
    **kwargs,
) -> Response:
    response = _validated_request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        stream=True,
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
        max_redirects=max_redirects,
        **kwargs,
    )
    return _buffer_response(response, raise_for_status=raise_for_status)


@contextmanager
def open_validated_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
    raise_for_status: bool = True,
    allow_redirects: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    max_redirects: int = 5,
    **kwargs,
) -> Generator[Response, None, None]:
    response = _validated_request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        stream=True,
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
        max_redirects=max_redirects,
        **kwargs,
    )
    with response:
        if raise_for_status:
            response.raise_for_status()
        yield response


@contextmanager
def open_asset_url(
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
    response = _asset_request_with_redirects(
        method,
        url,
        headers=headers,
        timeout=timeout,
        stream=True,
        max_redirects=max_redirects,
        **kwargs,
    )
    with response:
        if raise_for_status and not 200 <= response.status_code < 300:
            raise ValidationError(
                gettext(
                    "Unable to download asset from the provided URL (HTTP status code: %(code)s)."
                ),
                code="download_failed",
                params={"code": response.status_code},
            )
        yield response


def _probe_validated_url(
    url: str,
    *,
    timeout: float = 5,
    max_redirects: int = 5,
    validators: RedirectValidators,
) -> None:
    response = _request_with_redirects(
        "get",
        url,
        timeout=timeout,
        allow_redirects=True,
        stream=True,
        max_redirects=max_redirects,
        validators=validators,
    )
    with response:
        response.raise_for_status()


def _uri_error_cache_key(uri: str) -> str:
    return f"uri-check-{sha256(uri.encode()).hexdigest()}"


def format_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        return " ".join(
            message for messages in error.message_dict.values() for message in messages
        )
    return " ".join(error.messages)


def get_uri_error(uri: str) -> str | None:
    """Return error for fetching the URL or None if it works."""
    if uri.startswith("https://nonexisting.weblate.org/"):
        return "Non existing test URL"
    cache_key = _uri_error_cache_key(uri)
    cached = cache.get(cache_key)
    if cached is True:
        LOGGER.debug("URL check for %s, cached success", uri)
        return None
    if cached:
        # The cache contains string here
        LOGGER.debug("URL check for %s, cached failure", uri)
        return cached
    try:
        _probe_validated_url(
            uri,
            validators=RedirectValidators(),
            timeout=5,
            max_redirects=5,
        )
    except (requests.exceptions.RequestException, ValidationError) as error:
        if getattr(getattr(error, "response", None), "status_code", 0) == 429:
            # Silently ignore rate limiting issues
            return None
        result = (
            format_validation_error(error)
            if isinstance(error, ValidationError)
            else str(error)
        )
        cache.set(cache_key, result, 3600)
        return result
    cache.set(cache_key, True, 12 * 3600)
    LOGGER.debug("URL check for %s, tested success", uri)
    return None
