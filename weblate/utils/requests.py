# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared synchronous and asynchronous outbound HTTP handling."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address, ip_network
from typing import TYPE_CHECKING, Self
from urllib.parse import urlparse
from urllib.request import getproxies, proxy_bypass

import httpx2
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from opentelemetry import propagate
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from weblate.logger import LOGGER
from weblate.utils.outbound import (
    is_allowlisted_hostname,
    validate_connected_peer,
    validate_outbound_url,
    validate_runtime_url,
)
from weblate.utils.tracing import get_opentelemetry_tracer
from weblate.utils.validators import validate_asset_url

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator


@dataclass
class TestTransport:
    transport: httpx2.MockTransport | None = None


_TEST_TRANSPORT = TestTransport()
PEER_IP_RESPONSE_ATTR = "_weblate_peer_ip"
JSON_RESPONSE_ERRORS = (json.JSONDecodeError, UnicodeDecodeError)


def set_test_transport(transport: httpx2.MockTransport | None) -> None:
    """Override outbound transports in tests."""
    _TEST_TRANSPORT.transport = transport


@dataclass
class RedirectValidators:
    """Transport-neutral outbound request validation policy."""

    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        return

    def validate_response(self, response: httpx2.Response, *, used_proxy: bool) -> None:
        return


@dataclass
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

    def validate_response(self, response: httpx2.Response, *, used_proxy: bool) -> None:
        _validate_response_peer(
            response,
            allow_private_targets=self.allow_private_targets,
            allowed_domains=self.allowed_domains,
            used_proxy=used_proxy,
        )


@dataclass
class AssetRedirectValidators(RedirectValidators):
    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        validate_asset_url(request_url)


@dataclass
class RestrictedAssetRedirectValidators(RuntimeRedirectValidators):
    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        validate_asset_url(request_url)
        super().validate_request_url(request_url, used_proxy=used_proxy)


@dataclass
class ChainedRedirectValidators(RedirectValidators):
    request_validators: tuple[Callable[[str], None], ...] = ()
    response_validator: Callable[[httpx2.Response, bool], None] | None = None

    def validate_request_url(self, request_url: str, *, used_proxy: bool) -> None:
        for validator in self.request_validators:
            validator(request_url)

    def validate_response(self, response: httpx2.Response, *, used_proxy: bool) -> None:
        if self.response_validator is not None:
            self.response_validator(response, used_proxy)


def _prepare_headers(headers: dict[str, str] | None) -> dict[str, str]:
    # Lazy import avoids the version -> VCS -> HTTP import cycle during startup.
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.version import USER_AGENT

    agent = {"User-Agent": USER_AGENT}
    return {**headers, **agent} if headers is not None else agent


def _matches_no_proxy(hostname: str, port: int | None, no_proxy: str) -> bool:
    no_proxy_hosts = (host for host in no_proxy.replace(" ", "").split(",") if host)
    try:
        address = ip_address(hostname)
    except ValueError:
        host_with_port = hostname if port is None else f"{hostname}:{port}"
        for host in no_proxy_hosts:
            host = host.lstrip(".").lower()
            if host in {hostname, host_with_port}:
                return True
            suffix = f".{host}"
            if hostname.endswith(suffix) or host_with_port.endswith(suffix):
                return True
    else:
        for host in no_proxy_hosts:
            try:
                if address in ip_network(host, strict=False):
                    return True
            except ValueError:
                if hostname == host:
                    return True
    return False


def _get_proxy(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    proxies = getproxies()
    if (no_proxy := proxies.get("no")) and _matches_no_proxy(
        parsed.hostname, parsed.port, no_proxy
    ):
        return None
    if proxy_bypass(parsed.hostname):
        return None
    return proxies.get(parsed.scheme) or proxies.get("all")


def _request_uses_proxy(url: str) -> bool:
    return _get_proxy(url) is not None


def validate_request_url(
    url: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    RuntimeRedirectValidators(
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
    ).validate_request_url(url, used_proxy=_request_uses_proxy(url))


def _get_response_peer_ip(response: httpx2.Response) -> str | None:
    if peer_ip := getattr(response, PEER_IP_RESPONSE_ATTR, None):
        return str(peer_ip)
    try:
        stream = response.extensions["network_stream"]
        peer = stream.get_extra_info("server_addr")
    except (AttributeError, KeyError, OSError):
        return None

    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    if isinstance(peer, str):
        return peer
    return None


def _validate_response_peer(
    response: httpx2.Response,
    *,
    allow_private_targets: bool,
    allowed_domains: list[str] | tuple[str, ...] = (),
    used_proxy: bool = False,
) -> None:
    if allow_private_targets or used_proxy:
        return
    hostname = urlparse(str(response.url)).hostname or ""
    if is_allowlisted_hostname(hostname, allowed_domains):
        return
    validate_connected_peer(
        hostname,
        _get_response_peer_ip(response),
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
        used_proxy=used_proxy,
    )


def _normalize_request_kwargs(kwargs: dict) -> dict:
    result = kwargs.copy()
    data = result.get("data")
    if isinstance(data, str | bytes) and "files" not in result:
        result["content"] = result.pop("data")
    elif isinstance(data, Mapping):
        # Match Requests form encoding, which omitted mapping entries with null
        # values instead of sending them as empty fields.
        result["data"] = {
            key: value for key, value in data.items() if value is not None
        }
    # Requests accepted this argument per request. HTTPX2 transport selection is
    # handled centrally instead.
    result.pop("proxies", None)
    result.pop("verify", None)
    result.pop("cert", None)
    return result


@contextmanager
def trace_http_request(
    request: httpx2.Request,
) -> Generator[Span | None, None, None]:
    tracer = get_opentelemetry_tracer()
    if tracer is None:
        yield None
        return

    attributes: dict[str, str | int] = {
        "http.request.method": request.method,
        "server.address": request.url.host,
        "url.scheme": request.url.scheme,
    }
    if request.url.port is not None:
        attributes["server.port"] = request.url.port
    with tracer.start_as_current_span(
        f"{request.method} {request.url.host}",
        kind=SpanKind.CLIENT,
        attributes=attributes,
    ) as span:
        propagate.inject(request.headers)
        yield span


def record_http_response(span: Span | None, response: httpx2.Response) -> None:
    if span is None:
        return
    span.set_attribute("http.response.status_code", response.status_code)
    if response.is_error:
        span.set_status(Status(StatusCode.ERROR))


@contextmanager
def _close_response_on_error(
    response: httpx2.Response,
) -> Generator[None, None, None]:
    try:
        yield
    except Exception:
        response.close()
        raise


@asynccontextmanager
async def _aclose_response_on_error(
    response: httpx2.Response,
) -> AsyncGenerator[None]:
    try:
        yield
    except Exception:
        await response.aclose()
        raise


class HTTPClient:
    """Synchronous HTTPX2 client pool with per-hop proxy routing."""

    def __init__(self) -> None:
        self._clients: dict[str | None, httpx2.Client] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def _get_client(self, url: str) -> tuple[httpx2.Client, bool]:
        proxy = _get_proxy(url)
        client = self._clients.get(proxy)
        if client is None:
            transport: httpx2.BaseTransport
            if _TEST_TRANSPORT.transport is not None:
                transport = _TEST_TRANSPORT.transport
            else:
                transport = httpx2.HTTPTransport(proxy=proxy, trust_env=True)
            client = httpx2.Client(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            )
            self._clients[proxy] = client
        return client, proxy is not None

    def request(
        self,
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
    ) -> httpx2.Response:
        history: list[httpx2.Response] = []
        current_request: httpx2.Request | None = None
        request_kwargs = _normalize_request_kwargs(kwargs)
        request_auth = request_kwargs.pop("auth", None)

        for _ in range(max_redirects + 1):
            request_url = url if current_request is None else str(current_request.url)
            client, used_proxy = self._get_client(request_url)
            if validators is not None:
                validators.validate_request_url(request_url, used_proxy=used_proxy)

            if current_request is None:
                current_request = client.build_request(
                    method,
                    url,
                    headers=_prepare_headers(headers),
                    timeout=timeout,
                    **request_kwargs,
                )

            with trace_http_request(current_request) as span:
                response = client.send(
                    current_request,
                    stream=True,
                    follow_redirects=False,
                    auth=request_auth if not history else None,
                )
                record_http_response(span, response)
                response.history = history.copy()
                with _close_response_on_error(response):
                    if validators is not None:
                        validators.validate_response(response, used_proxy=used_proxy)

                    next_request = response.next_request
                    if not allow_redirects or next_request is None:
                        if not stream:
                            response.read()
                            response.close()
                        return response

                    history.append(response)
                    response.close()
                    current_request = next_request

        msg = f"Exceeded {max_redirects} redirects."
        raise httpx2.TooManyRedirects(msg, request=current_request)


class AsyncHTTPClient:
    """Asynchronous HTTPX2 client pool with the same validation policy."""

    def __init__(self) -> None:
        self._clients: dict[str | None, httpx2.AsyncClient] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    def _get_client(self, url: str) -> tuple[httpx2.AsyncClient, bool]:
        proxy = _get_proxy(url)
        client = self._clients.get(proxy)
        if client is None:
            transport: httpx2.AsyncBaseTransport
            if _TEST_TRANSPORT.transport is not None:
                transport = _TEST_TRANSPORT.transport
            else:
                transport = httpx2.AsyncHTTPTransport(proxy=proxy, trust_env=True)
            client = httpx2.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            )
            self._clients[proxy] = client
        return client, proxy is not None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5,  # ruff: ignore[async-function-with-timeout]
        allow_redirects: bool = True,
        stream: bool = False,
        max_redirects: int = 5,
        validators: RedirectValidators | None = None,
        **kwargs,
    ) -> httpx2.Response:
        history: list[httpx2.Response] = []
        current_request: httpx2.Request | None = None
        request_kwargs = _normalize_request_kwargs(kwargs)
        request_auth = request_kwargs.pop("auth", None)

        for _ in range(max_redirects + 1):
            request_url = url if current_request is None else str(current_request.url)
            client, used_proxy = self._get_client(request_url)
            if validators is not None:
                await sync_to_async(
                    validators.validate_request_url,
                    thread_sensitive=False,
                )(request_url, used_proxy=used_proxy)

            if current_request is None:
                current_request = client.build_request(
                    method,
                    url,
                    headers=_prepare_headers(headers),
                    timeout=timeout,
                    **request_kwargs,
                )

            with trace_http_request(current_request) as span:
                response = await client.send(
                    current_request,
                    stream=True,
                    follow_redirects=False,
                    auth=request_auth if not history else None,
                )
                record_http_response(span, response)
                response.history = history.copy()
                async with _aclose_response_on_error(response):
                    if validators is not None:
                        validators.validate_response(response, used_proxy=used_proxy)

                    next_request = response.next_request
                    if not allow_redirects or next_request is None:
                        if not stream:
                            await response.aread()
                            await response.aclose()
                        return response

                    history.append(response)
                    await response.aclose()
                    current_request = next_request

        msg = f"Exceeded {max_redirects} redirects."
        raise httpx2.TooManyRedirects(msg, request=current_request)


def _request_with_redirects(
    method: str,
    url: str,
    **kwargs,
) -> httpx2.Response:
    with HTTPClient() as client:
        return client.request(method, url, **kwargs)


async def _async_request_with_redirects(
    method: str,
    url: str,
    **kwargs,
) -> httpx2.Response:
    async with AsyncHTTPClient() as client:
        return await client.request(method, url, **kwargs)


def _validated_request_with_redirects(
    method: str,
    url: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    return _request_with_redirects(
        method,
        url,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        ),
        **kwargs,
    )


async def _async_validated_request_with_redirects(
    method: str,
    url: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    return await _async_request_with_redirects(
        method,
        url,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            allowed_domains=allowed_domains,
        ),
        **kwargs,
    )


def fetch_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    **kwargs,
) -> httpx2.Response:
    response = _request_with_redirects(method, url, stream=False, **kwargs)
    if raise_for_status:
        response.raise_for_status()
    return response


async def async_fetch_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    **kwargs,
) -> httpx2.Response:
    response = await _async_request_with_redirects(method, url, stream=False, **kwargs)
    if raise_for_status:
        response.raise_for_status()
    return response


def fetch_validated_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    response = _validated_request_with_redirects(
        method,
        url,
        stream=False,
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
        **kwargs,
    )
    if raise_for_status:
        response.raise_for_status()
    return response


async def async_fetch_validated_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    response = await _async_validated_request_with_redirects(
        method,
        url,
        stream=False,
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
        **kwargs,
    )
    if raise_for_status:
        response.raise_for_status()
    return response


@contextmanager
def open_validated_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> Generator[httpx2.Response, None, None]:
    with HTTPClient() as client:
        response = client.request(
            method,
            url,
            stream=True,
            validators=RuntimeRedirectValidators(
                allow_private_targets=allow_private_targets,
                allowed_domains=allowed_domains,
            ),
            **kwargs,
        )
        try:
            if raise_for_status:
                response.raise_for_status()
            yield response
        finally:
            response.close()


@asynccontextmanager
async def async_open_validated_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> AsyncGenerator[httpx2.Response]:
    async with AsyncHTTPClient() as client:
        response = await client.request(
            method,
            url,
            stream=True,
            validators=RuntimeRedirectValidators(
                allow_private_targets=allow_private_targets,
                allowed_domains=allowed_domains,
            ),
            **kwargs,
        )
        try:
            if raise_for_status:
                response.raise_for_status()
            yield response
        finally:
            await response.aclose()


@contextmanager
def open_asset_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    **kwargs,
) -> Generator[httpx2.Response, None, None]:
    with HTTPClient() as client:
        response = client.request(
            method,
            url,
            stream=True,
            validators=AssetRedirectValidators(),
            **kwargs,
        )
        try:
            if raise_for_status and not response.is_success:
                raise ValidationError(
                    gettext(
                        "Unable to download asset from the provided URL (HTTP status code: %(code)s)."
                    ),
                    code="download_failed",
                    params={"code": response.status_code},
                )
            yield response
        finally:
            response.close()


@contextmanager
def open_restricted_asset_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> Generator[httpx2.Response, None, None]:
    with HTTPClient() as client:
        response = client.request(
            method,
            url,
            stream=True,
            validators=RestrictedAssetRedirectValidators(
                allow_private_targets=allow_private_targets,
                allowed_domains=allowed_domains,
            ),
            **kwargs,
        )
        try:
            if raise_for_status and not response.is_success:
                raise ValidationError(
                    gettext(
                        "Unable to download asset from the provided URL (HTTP status code: %(code)s)."
                    ),
                    code="download_failed",
                    params={"code": response.status_code},
                )
            yield response
        finally:
            response.close()


def _probe_validated_url(
    url: str,
    *,
    timeout: float = 5,
    max_redirects: int = 5,
    validators: RedirectValidators,
) -> None:
    with HTTPClient() as client:
        response = client.request(
            "get",
            url,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
            max_redirects=max_redirects,
            validators=validators,
        )
        try:
            response.raise_for_status()
        finally:
            response.close()


def _uri_error_cache_key(
    uri: str,
    *,
    allow_private_targets: bool,
    allowed_domains: list[str] | tuple[str, ...],
) -> str:
    policy = f"{allow_private_targets}:{tuple(sorted(allowed_domains))}:{uri}"
    return f"uri-check-{sha256(policy.encode()).hexdigest()}"


def format_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        return " ".join(
            message for messages in error.message_dict.values() for message in messages
        )
    return " ".join(error.messages)


def get_uri_error(
    uri: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> str | None:
    """Return error for fetching the URL or None if it works."""
    if uri.startswith("https://nonexisting.weblate.org/"):
        return "Non existing test URL"
    cache_key = _uri_error_cache_key(
        uri,
        allow_private_targets=allow_private_targets,
        allowed_domains=allowed_domains,
    )
    cached = cache.get(cache_key)
    if cached is True:
        LOGGER.debug("URL check for %s, cached success", uri)
        return None
    if cached:
        LOGGER.debug("URL check for %s, cached failure", uri)
        return cached
    try:
        _probe_validated_url(
            uri,
            validators=RuntimeRedirectValidators(
                allow_private_targets=allow_private_targets,
                allowed_domains=allowed_domains,
            ),
        )
    except (httpx2.HTTPError, ValidationError) as error:
        if getattr(getattr(error, "response", None), "status_code", 0) == 429:
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
