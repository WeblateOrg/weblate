# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared synchronous and asynchronous outbound HTTP handling."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

import httpx2
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.logger import LOGGER
from weblate.utils.outbound import (
    async_resolve_runtime_hostname,
    get_environment_proxy,
    is_allowlisted_hostname,
    resolve_runtime_hostname,
    validate_connected_peer,
    validate_outbound_url,
)
from weblate.utils.validators import validate_asset_url

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        Callable,
        Iterator,
    )
    from typing import Any, Never

    from httpx2._types import AuthTypes


@dataclass
class TestTransport:
    transport: httpx2.MockTransport | None = None


_TEST_TRANSPORT = TestTransport()
PEER_IP_RESPONSE_ATTR = "_weblate_peer_ip"
ORIGINAL_URL_REQUEST_EXTENSION = "weblate_original_url"
JSON_RESPONSE_ERRORS = (json.JSONDecodeError, UnicodeDecodeError)
ADDRESS_FALLBACK_DELAY = 0.25
MAX_REDIRECTS = 5
DEFAULT_RESPONSE_SIZE = 2 * 1024 * 1024
MACHINERY_RESPONSE_SIZE = 1024 * 1024
VCS_RESPONSE_SIZE = 16 * 1024 * 1024
TESSERACT_RESPONSE_SIZE = 64 * 1024 * 1024


class ResponseTooLarge(httpx2.DecodingError):
    """An HTTP response exceeded its caller's decoded-byte budget."""


def check_response_size(response: httpx2.Response, size: int, maximum: int) -> None:
    if size > maximum:
        msg = f"HTTP response exceeds the {maximum}-byte decoded size limit."
        raise ResponseTooLarge(msg, request=response.request)


async def async_read_response_content(response: httpx2.Response, maximum: int) -> bytes:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        check_response_size(response, len(content) + len(chunk), maximum)
        content.extend(chunk)
    return bytes(content)


def buffered_response(response: httpx2.Response, content: bytes) -> httpx2.Response:
    """Build a buffered response using public HTTPX APIs without decoding twice."""
    try:
        _ = response.content
    except httpx2.ResponseNotRead:
        pass
    else:
        return response
    headers = response.headers.copy()
    headers.pop("Content-Encoding", None)
    buffered = httpx2.Response(
        response.status_code,
        content=content,
        headers=headers,
        request=response.request,
        extensions=response.extensions,
        history=response.history,
        default_encoding=response.default_encoding,
    )
    # Keep wire headers available to callers after installing the decoded body.
    buffered.headers = response.headers.copy()
    buffered.next_request = response.next_request
    # Manually constructed responses need not have elapsed timing.
    with suppress(RuntimeError):
        buffered.elapsed = response.elapsed
    return buffered


def set_test_transport(transport: httpx2.MockTransport | None) -> None:
    """Override outbound transports in tests."""
    _TEST_TRANSPORT.transport = transport


@dataclass
class RedirectValidators:
    """Transport-neutral outbound request validation policy."""

    def validate_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        """Validate a request and return addresses to pin, when needed."""
        return ()

    async def validate_async_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        """Asynchronously validate a request and return addresses to pin."""
        return self.validate_request_url(request_url, used_proxy=used_proxy)

    def validate_response(self, response: httpx2.Response, *, used_proxy: bool) -> None:
        return


@dataclass
class RuntimeRedirectValidators(RedirectValidators):
    allow_private_targets: bool = False
    private_allowlist: list[str] | tuple[str, ...] = ()

    def _get_hostname_to_resolve(
        self, request_url: str, *, used_proxy: bool
    ) -> str | None:
        hostname = urlparse(request_url).hostname or ""
        if is_allowlisted_hostname(hostname, self.private_allowlist):
            validate_outbound_url(
                request_url,
                allow_private_targets=False,
                private_allowlist=self.private_allowlist,
            )
            return None
        if used_proxy:
            validate_outbound_url(
                request_url,
                allow_private_targets=self.allow_private_targets,
                private_allowlist=self.private_allowlist,
            )
            return None
        return hostname

    def validate_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        hostname = self._get_hostname_to_resolve(request_url, used_proxy=used_proxy)
        if hostname is None:
            return ()
        return resolve_runtime_hostname(
            hostname, allow_private_targets=self.allow_private_targets
        )

    async def validate_async_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        hostname = self._get_hostname_to_resolve(request_url, used_proxy=used_proxy)
        if hostname is None:
            return ()
        return await async_resolve_runtime_hostname(
            hostname, allow_private_targets=self.allow_private_targets
        )

    def validate_response(self, response: httpx2.Response, *, used_proxy: bool) -> None:
        _validate_response_peer(
            response,
            allow_private_targets=self.allow_private_targets,
            private_allowlist=self.private_allowlist,
            used_proxy=used_proxy,
        )


@dataclass
class RestrictedAssetRedirectValidators(RuntimeRedirectValidators):
    def validate_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        validate_asset_url(request_url)
        return super().validate_request_url(request_url, used_proxy=used_proxy)

    async def validate_async_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        validate_asset_url(request_url)
        return await super().validate_async_request_url(
            request_url, used_proxy=used_proxy
        )


def _prepare_headers(headers: dict[str, str] | None) -> dict[str, str]:
    # Lazy import avoids the version -> VCS -> HTTP import cycle during startup.
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.version import USER_AGENT

    agent = {"User-Agent": USER_AGENT}
    return {**headers, **agent} if headers is not None else agent


def validate_request_url(
    url: str,
    *,
    allow_private_targets: bool = True,
    private_allowlist: list[str] | tuple[str, ...] = (),
) -> None:
    RuntimeRedirectValidators(
        allow_private_targets=allow_private_targets,
        private_allowlist=private_allowlist,
    ).validate_request_url(url, used_proxy=get_environment_proxy(url) is not None)


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
    private_allowlist: list[str] | tuple[str, ...] = (),
    used_proxy: bool = False,
) -> None:
    if allow_private_targets or used_proxy:
        return
    hostname = urlparse(str(response.url)).hostname or ""
    if is_allowlisted_hostname(hostname, private_allowlist):
        return
    validate_connected_peer(
        hostname,
        _get_response_peer_ip(response),
        allow_private_targets=allow_private_targets,
        private_allowlist=private_allowlist,
        used_proxy=used_proxy,
    )


def _build_pinned_request(
    request: httpx2.Request, connection_address: str
) -> httpx2.Request:
    """Clone a request for a validated address while retaining its HTTP origin."""
    extensions = {
        **request.extensions,
        ORIGINAL_URL_REQUEST_EXTENSION: request.url,
        "sni_hostname": request.url.raw_host.decode("ascii"),
    }
    return httpx2.Request(
        method=request.method,
        url=request.url.copy_with(host=connection_address),
        headers=request.headers,
        stream=request.stream,
        extensions=extensions,
    )


def _transport_key(
    request: httpx2.Request,
    *,
    proxy: str | None,
    connection_address: str | None,
) -> tuple[str, ...]:
    if proxy is not None:
        return ("proxy", proxy)
    if connection_address is None:
        return ("direct",)
    return (
        "pinned",
        request.url.scheme,
        request.url.host,
        str(request.url.port or ""),
        connection_address,
    )


class OutboundTransportPool[
    TransportType: httpx2.BaseTransport | httpx2.AsyncBaseTransport
]:
    """Share outbound transport selection and connection-pool isolation."""

    def __init__(
        self,
        transport: TransportType | None,
        transport_factory: Callable[[str | None], TransportType],
    ) -> None:
        self.transport_override = transport or cast(
            "TransportType | None", _TEST_TRANSPORT.transport
        )
        self.transport_factory = transport_factory
        self.transports: dict[tuple[str, ...], TransportType] = {}

    def get(
        self,
        request: httpx2.Request,
        *,
        proxy: str | None,
        connection_address: str | None,
    ) -> TransportType:
        if self.transport_override is not None:
            return self.transport_override
        key = _transport_key(
            request,
            proxy=proxy,
            connection_address=connection_address,
        )
        if (transport := self.transports.get(key)) is None:
            transport = self.transport_factory(proxy)
            self.transports[key] = transport
        return transport

    def active(self) -> list[TransportType]:
        if self.transport_override is not None:
            return [self.transport_override]
        return list(self.transports.values())

    def clear(self) -> None:
        self.transports.clear()


@dataclass(frozen=True)
class OutboundRequest:
    """Transport-neutral details used to validate and route a request."""

    url: str
    proxy: str | None

    @property
    def used_proxy(self) -> bool:
        return self.proxy is not None


def _prepare_outbound_request(request: httpx2.Request) -> OutboundRequest:
    request_url = str(request.url)
    return OutboundRequest(
        url=request_url,
        proxy=get_environment_proxy(request_url),
    )


async def _validate_async_outbound_request(
    outbound: OutboundRequest,
    validators: RedirectValidators | None,
) -> tuple[str, ...]:
    if validators is None:
        return ()
    return await validators.validate_async_request_url(
        outbound.url,
        used_proxy=outbound.used_proxy,
    )


def _route_outbound_request[
    TransportType: httpx2.BaseTransport | httpx2.AsyncBaseTransport
](
    pool: OutboundTransportPool[TransportType],
    request: httpx2.Request,
    connection_addresses: tuple[str, ...],
    *,
    proxy: str | None,
) -> tuple[tuple[TransportType, httpx2.Request], ...]:
    addresses: tuple[str | None, ...] = connection_addresses or (None,)
    return tuple(
        (
            pool.get(
                request,
                proxy=proxy,
                connection_address=connection_address,
            ),
            (
                _build_pinned_request(request, connection_address)
                if connection_address is not None
                else request
            ),
        )
        for connection_address in addresses
    )


def _connection_deadline[
    TransportType: httpx2.BaseTransport | httpx2.AsyncBaseTransport
](
    routes: tuple[tuple[TransportType, httpx2.Request], ...],
) -> float | None:
    if len(routes) == 1:
        return None
    connect_timeout = routes[0][1].extensions.get("timeout", {}).get("connect")
    if connect_timeout is None:
        return None
    return monotonic() + float(connect_timeout)


def _set_attempt_connect_timeout(
    request: httpx2.Request,
    *,
    deadline: float | None,
    probe: bool,
) -> None:
    if deadline is None:
        connect_timeout = ADDRESS_FALLBACK_DELAY if probe else None
    else:
        remaining = max(0.0, deadline - monotonic())
        connect_timeout = min(ADDRESS_FALLBACK_DELAY, remaining) if probe else remaining
    timeouts = dict(request.extensions.get("timeout", {}))
    timeouts["connect"] = connect_timeout
    request.extensions["timeout"] = timeouts


def _connection_budget_exhausted(deadline: float | None) -> bool:
    return deadline is not None and monotonic() >= deadline


class _ConnectionFallback[
    TransportType: httpx2.BaseTransport | httpx2.AsyncBaseTransport
]:
    """
    Track fast probes and retries within one request's connection budget.

    AnyIO's Happy Eyeballs API resolves hostnames itself and cannot accept the
    address set already approved by the SSRF validator.
    """

    def __init__(
        self,
        routes: tuple[tuple[TransportType, httpx2.Request], ...],
    ) -> None:
        self.routes = routes
        self.deadline = _connection_deadline(routes)
        self.timed_out_routes: list[tuple[TransportType, httpx2.Request]] = []
        self.last_error: httpx2.ConnectError | httpx2.ConnectTimeout | None = None

    def attempts(
        self,
    ) -> Iterator[tuple[TransportType, httpx2.Request, bool]]:
        for probe, routes in (
            (True, self.routes),
            (False, self.timed_out_routes),
        ):
            for transport, request in routes:
                _set_attempt_connect_timeout(
                    request,
                    deadline=self.deadline,
                    probe=probe,
                )
                yield transport, request, probe

    def record_failure(
        self,
        route: tuple[TransportType, httpx2.Request],
        error: httpx2.ConnectError | httpx2.ConnectTimeout,
        *,
        probe: bool,
    ) -> None:
        if probe and isinstance(error, httpx2.ConnectTimeout):
            self.timed_out_routes.append(route)
        self.last_error = error
        if _connection_budget_exhausted(self.deadline):
            raise error

    def raise_last_error(self) -> Never:
        if self.last_error is not None:
            raise self.last_error
        msg = "No outbound routes available."
        raise RuntimeError(msg)


async def _send_async_request_with_fallback(
    routes: tuple[tuple[httpx2.AsyncBaseTransport, httpx2.Request], ...],
) -> httpx2.Response:
    if len(routes) == 1:
        transport, request = routes[0]
        return await transport.handle_async_request(request)

    fallback = _ConnectionFallback(routes)
    for transport, request, probe in fallback.attempts():
        try:
            return await transport.handle_async_request(request)
        except (httpx2.ConnectError, httpx2.ConnectTimeout) as error:
            fallback.record_failure(
                (transport, request),
                error,
                probe=probe,
            )
    return fallback.raise_last_error()


def _validate_transport_response(
    response: httpx2.Response,
    *,
    request: httpx2.Request,
    validators: RedirectValidators | None,
    used_proxy: bool,
) -> None:
    response.request = request
    if validators is not None:
        validators.validate_response(response, used_proxy=used_proxy)


class AsyncOutboundHTTPTransport(httpx2.AsyncBaseTransport):
    """Validate and route every asynchronous HTTPX2 request hop."""

    def __init__(
        self,
        transport: httpx2.AsyncBaseTransport | None = None,
        *,
        validators: RedirectValidators | None = None,
    ) -> None:
        self.validators = validators
        self.pool = OutboundTransportPool(
            transport,
            lambda proxy: httpx2.AsyncHTTPTransport(proxy=proxy, trust_env=True),
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        outbound = _prepare_outbound_request(request)
        connection_addresses = await _validate_async_outbound_request(
            outbound, self.validators
        )
        routes = _route_outbound_request(
            self.pool,
            request,
            connection_addresses,
            proxy=outbound.proxy,
        )
        response = await _send_async_request_with_fallback(routes)
        try:
            _validate_transport_response(
                response,
                request=request,
                validators=self.validators,
                used_proxy=outbound.used_proxy,
            )
        except BaseException:
            await response.aclose()
            raise
        return response

    async def aclose(self) -> None:
        for transport in self.pool.active():
            await transport.aclose()
        self.pool.clear()


def create_async_http_client(
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    validators: RedirectValidators | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx2.AsyncClient:
    """Create an asynchronous HTTPX2 client using Weblate's outbound transport."""
    return httpx2.AsyncClient(
        headers=_prepare_headers(None),
        transport=AsyncOutboundHTTPTransport(transport, validators=validators),
        trust_env=False,
        follow_redirects=False,
        max_redirects=max_redirects,
    )


def _build_client_request(
    client: httpx2.Client | httpx2.AsyncClient,
    method: str,
    url: str,
    *,
    kwargs: dict,
) -> tuple[httpx2.Request, AuthTypes | None]:
    request_kwargs = kwargs.copy()
    request_auth = request_kwargs.pop("auth", None)
    request = client.build_request(
        method,
        url,
        **request_kwargs,
    )
    return request, request_auth


def _next_streaming_redirect(
    response: httpx2.Response,
    history: list[httpx2.Response],
    max_redirects: int,
) -> httpx2.Request | None:
    """Return HTTPX's next redirect request without consuming the response."""
    response.history = list(history)
    next_request = response.next_request
    if next_request is None:
        return None

    history.append(response)
    if len(history) > max_redirects:
        msg = "Exceeded maximum allowed redirects."
        raise httpx2.TooManyRedirects(
            msg,
            request=next_request,
        )
    return next_request


async def _async_send_with_redirects(
    client: httpx2.AsyncClient,
    request: httpx2.Request,
    *,
    auth: AuthTypes | None,
) -> httpx2.Response:
    history: list[httpx2.Response] = []
    while True:
        response = await client.send(
            request,
            stream=True,
            auth=auth,
            follow_redirects=False,
        )
        try:
            next_request = _next_streaming_redirect(
                response, history, client.max_redirects
            )
        except BaseException:
            await response.aclose()
            raise
        if next_request is None:
            return response
        await response.aclose()
        request = next_request
        auth = None


@asynccontextmanager
async def _request_deadline(request: httpx2.Request) -> AsyncGenerator[None, None]:
    """Distinguish expiry of this deadline from consumer errors or cancellation."""
    deadline = asyncio.timeout(request.extensions.get("timeout", {}).get("read"))
    try:
        async with deadline:
            yield
    except TimeoutError as error:
        if not deadline.expired():
            raise
        msg = "HTTP request exceeded its total timeout."
        raise httpx2.TimeoutException(msg, request=request) from error


@asynccontextmanager
async def async_open_url(
    method: str,
    url: str,
    *,
    validators: RedirectValidators | None = None,
    follow_redirects: bool = True,
    raise_for_status: bool = True,
    **kwargs: Any,  # ruff: ignore[any-type]
) -> AsyncGenerator[httpx2.Response, None]:
    """Own the response stream and one deadline across every request hop."""
    async with create_async_http_client(validators=validators) as client:
        request, request_auth = _build_client_request(
            client, method, url, kwargs=kwargs
        )
        # HTTPX records the effective timeout, including its default or None.
        # Structured Timeouts use read as the total budget. System DNS and
        # executor shutdown can delay return even after cancellation.
        async with _request_deadline(request):
            response = (
                await _async_send_with_redirects(client, request, auth=request_auth)
                if follow_redirects
                else await client.send(
                    request, stream=True, auth=request_auth, follow_redirects=False
                )
            )
            try:
                if raise_for_status:
                    response.raise_for_status()
                yield response
            finally:
                await response.aclose()


def _request(
    method: str,
    url: str,
    **kwargs: Any,  # ruff: ignore[any-type]
) -> httpx2.Response:
    """Finish asynchronous I/O before returning to a synchronous caller."""
    return async_to_sync(_async_request)(method, url, **kwargs)


async def _async_request(
    method: str,
    url: str,
    *,
    max_response_size: int = DEFAULT_RESPONSE_SIZE,
    **kwargs: Any,  # ruff: ignore[any-type]
) -> httpx2.Response:
    async with async_open_url(
        method, url, raise_for_status=False, **kwargs
    ) as response:
        content = await async_read_response_content(response, max_response_size)
        return buffered_response(response, content)


def fetch_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    follow_redirects: bool = True,
    **kwargs,
) -> httpx2.Response:
    response = _request(method, url, follow_redirects=follow_redirects, **kwargs)
    if raise_for_status:
        response.raise_for_status()
    return response


async def async_fetch_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    follow_redirects: bool = True,
    **kwargs,
) -> httpx2.Response:
    response = await _async_request(
        method, url, follow_redirects=follow_redirects, **kwargs
    )
    if raise_for_status:
        response.raise_for_status()
    return response


def fetch_validated_url(
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    follow_redirects: bool = True,
    allow_private_targets: bool = False,
    private_allowlist: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    response = _request(
        method,
        url,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            private_allowlist=private_allowlist,
        ),
        follow_redirects=follow_redirects,
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
    follow_redirects: bool = True,
    allow_private_targets: bool = False,
    private_allowlist: list[str] | tuple[str, ...] = (),
    **kwargs,
) -> httpx2.Response:
    response = await _async_request(
        method,
        url,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            private_allowlist=private_allowlist,
        ),
        follow_redirects=follow_redirects,
        **kwargs,
    )
    if raise_for_status:
        response.raise_for_status()
    return response


@asynccontextmanager
async def async_open_validated_url(
    method: str,
    url: str,
    *,
    allow_private_targets: bool = False,
    private_allowlist: list[str] | tuple[str, ...] = (),
    **kwargs: Any,  # ruff: ignore[any-type]
) -> AsyncGenerator[httpx2.Response, None]:
    """Validate each redirect and keep body consumption inside the deadline."""
    async with async_open_url(
        method,
        url,
        validators=RuntimeRedirectValidators(
            allow_private_targets=allow_private_targets,
            private_allowlist=private_allowlist,
        ),
        **kwargs,
    ) as response:
        yield response


async def _async_fetch_restricted_asset_url(
    method: str,
    url: str,
    *,
    max_response_size: int,
    raise_for_status: bool,
    allow_private_targets: bool,
    private_allowlist: list[str] | tuple[str, ...],
    **kwargs: Any,  # ruff: ignore[any-type]
) -> httpx2.Response:
    async with async_open_url(
        method,
        url,
        validators=RestrictedAssetRedirectValidators(
            allow_private_targets=allow_private_targets,
            private_allowlist=private_allowlist,
        ),
        raise_for_status=False,
        **kwargs,
    ) as response:
        if raise_for_status and not response.is_success:
            raise ValidationError(
                gettext(
                    "Unable to download asset from the provided URL (HTTP status code: %(code)s)."
                ),
                code="download_failed",
                params={"code": response.status_code},
            )
        content = await async_read_response_content(response, max_response_size)
        return buffered_response(response, content)


def fetch_restricted_asset_url(
    method: str,
    url: str,
    *,
    max_response_size: int | None = None,
    raise_for_status: bool = True,
    allow_private_targets: bool = False,
    private_allowlist: list[str] | tuple[str, ...] = (),
    **kwargs: Any,  # ruff: ignore[any-type]
) -> httpx2.Response:
    """Return a bounded asset after validating and closing its network stream."""
    return async_to_sync(_async_fetch_restricted_asset_url)(
        method,
        url,
        max_response_size=settings.ALLOWED_ASSET_SIZE
        if max_response_size is None
        else max_response_size,
        raise_for_status=raise_for_status,
        allow_private_targets=allow_private_targets,
        private_allowlist=private_allowlist,
        **kwargs,
    )


async def _async_probe_validated_url(
    url: str, *, request_timeout: float, validators: RedirectValidators
) -> None:
    async with async_open_url(
        "get", url, timeout=request_timeout, validators=validators
    ):
        pass


def _probe_validated_url(
    url: str,
    *,
    timeout: float = 5,
    validators: RedirectValidators,
) -> None:
    async_to_sync(_async_probe_validated_url)(
        url, request_timeout=timeout, validators=validators
    )


def _uri_error_cache_key(
    uri: str,
    *,
    allow_private_targets: bool,
    private_allowlist: list[str] | tuple[str, ...],
) -> str:
    policy = f"{allow_private_targets}:{tuple(sorted(private_allowlist))}:{uri}"
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
    private_allowlist: list[str] | tuple[str, ...] = (),
) -> str | None:
    """Return error for fetching the URL or None if it works."""
    if uri.startswith("https://nonexisting.weblate.org/"):
        return "Non existing test URL"
    cache_key = _uri_error_cache_key(
        uri,
        allow_private_targets=allow_private_targets,
        private_allowlist=private_allowlist,
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
                private_allowlist=private_allowlist,
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
