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
from time import monotonic
from typing import TYPE_CHECKING, Any, Self, cast
from urllib.parse import urlparse
from urllib.request import getproxies, proxy_bypass

import httpx2
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from opentelemetry import propagate
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from weblate.logger import LOGGER
from weblate.utils.outbound import (
    async_resolve_runtime_hostname,
    is_allowlisted_hostname,
    resolve_runtime_hostname,
    validate_connected_peer,
    validate_outbound_url,
)
from weblate.utils.tracing import get_opentelemetry_tracer
from weblate.utils.validators import validate_asset_url

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Callable,
        Generator,
        Iterator,
    )
    from types import TracebackType
    from typing import Never

    from httpx2._types import AuthTypes


@dataclass
class TestTransport:
    transport: httpx2.MockTransport | None = None


_TEST_TRANSPORT = TestTransport()
PEER_IP_RESPONSE_ATTR = "_weblate_peer_ip"
ORIGINAL_URL_REQUEST_EXTENSION = "weblate_original_url"
VALIDATORS_REQUEST_EXTENSION = "weblate_redirect_validators"
JSON_RESPONSE_ERRORS = (json.JSONDecodeError, UnicodeDecodeError)
ADDRESS_FALLBACK_DELAY = 0.25


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
    allow_private_targets: bool = True
    allowed_domains: list[str] | tuple[str, ...] = ()

    def _get_hostname_to_resolve(
        self, request_url: str, *, used_proxy: bool
    ) -> str | None:
        hostname = urlparse(request_url).hostname or ""
        if is_allowlisted_hostname(hostname, self.allowed_domains):
            validate_outbound_url(
                request_url,
                allow_private_targets=False,
                allowed_domains=self.allowed_domains,
            )
            return None
        if used_proxy:
            validate_outbound_url(
                request_url,
                allow_private_targets=self.allow_private_targets,
                allowed_domains=self.allowed_domains,
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
            allowed_domains=self.allowed_domains,
            used_proxy=used_proxy,
        )


@dataclass
class AssetRedirectValidators(RedirectValidators):
    def validate_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        validate_asset_url(request_url)
        return ()


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


@dataclass
class ChainedRedirectValidators(RedirectValidators):
    request_validators: tuple[Callable[[str], None], ...] = ()
    response_validator: Callable[[httpx2.Response, bool], None] | None = None

    def validate_request_url(
        self, request_url: str, *, used_proxy: bool
    ) -> tuple[str, ...]:
        for validator in self.request_validators:
            validator(request_url)
        return ()

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


class TracedStream:
    """Keep a client span open until its response stream is consumed."""

    def __init__(self, trace) -> None:
        self.trace = trace

    def _finish(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.trace is not None:
            trace, self.trace = self.trace, None
            trace.__exit__(exc_type, exc_value, traceback)


class TracedSyncStream(TracedStream, httpx2.SyncByteStream):
    """Synchronous traced response stream."""

    def __init__(self, stream: httpx2.SyncByteStream, trace) -> None:
        super().__init__(trace)
        self.stream = stream

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self.stream
        except BaseException as error:
            self._finish(type(error), error, error.__traceback__)
            raise
        self._finish()

    def close(self) -> None:
        try:
            self.stream.close()
        except BaseException as error:
            self._finish(type(error), error, error.__traceback__)
            raise
        self._finish()


class TracedAsyncStream(TracedStream, httpx2.AsyncByteStream):
    """Asynchronous traced response stream."""

    def __init__(self, stream: httpx2.AsyncByteStream, trace) -> None:
        super().__init__(trace)
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.stream:
                yield chunk
        except BaseException as error:
            self._finish(type(error), error, error.__traceback__)
            raise
        self._finish()

    async def aclose(self) -> None:
        try:
            await self.stream.aclose()
        except BaseException as error:
            self._finish(type(error), error, error.__traceback__)
            raise
        self._finish()


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
    validators: RedirectValidators | None

    @property
    def used_proxy(self) -> bool:
        return self.proxy is not None


def _prepare_outbound_request(request: httpx2.Request) -> OutboundRequest:
    request_url = str(request.url)
    return OutboundRequest(
        url=request_url,
        proxy=_get_proxy(request_url),
        validators=cast(
            "RedirectValidators | None",
            request.extensions.get(VALIDATORS_REQUEST_EXTENSION),
        ),
    )


async def _validate_async_outbound_request(
    outbound: OutboundRequest,
) -> tuple[str, ...]:
    if outbound.validators is None:
        return ()
    return await outbound.validators.validate_async_request_url(
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


def _send_request_with_fallback(
    routes: tuple[tuple[httpx2.BaseTransport, httpx2.Request], ...],
) -> httpx2.Response:
    if len(routes) == 1:
        transport, request = routes[0]
        return transport.handle_request(request)

    fallback = _ConnectionFallback(routes)
    for transport, request, probe in fallback.attempts():
        try:
            return transport.handle_request(request)
        except (httpx2.ConnectError, httpx2.ConnectTimeout) as error:
            fallback.record_failure(
                (transport, request),
                error,
                probe=probe,
            )
    return fallback.raise_last_error()


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
    span: Span | None,
    validators: RedirectValidators | None,
    used_proxy: bool,
) -> None:
    response.request = request
    record_http_response(span, response)
    if validators is not None:
        validators.validate_response(response, used_proxy=used_proxy)


class OutboundHTTPTransport(httpx2.BaseTransport):
    """Validate and route every synchronous HTTPX2 request hop."""

    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        self.pool = OutboundTransportPool(
            transport,
            lambda proxy: httpx2.HTTPTransport(proxy=proxy, trust_env=True),
        )

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        outbound = _prepare_outbound_request(request)
        connection_addresses = (
            outbound.validators.validate_request_url(
                outbound.url, used_proxy=outbound.used_proxy
            )
            if outbound.validators is not None
            else ()
        )
        trace = trace_http_request(request)
        span = trace.__enter__()  # ruff: ignore[unnecessary-dunder-call]
        response: httpx2.Response | None = None
        try:
            routes = _route_outbound_request(
                self.pool,
                request,
                connection_addresses,
                proxy=outbound.proxy,
            )
            response = _send_request_with_fallback(routes)
            _validate_transport_response(
                response,
                request=request,
                span=span,
                validators=outbound.validators,
                used_proxy=outbound.used_proxy,
            )
            response.stream = TracedSyncStream(
                cast("httpx2.SyncByteStream", response.stream), trace
            )
        except BaseException as error:
            try:
                if response is not None:
                    response.close()
            finally:
                trace.__exit__(type(error), error, error.__traceback__)
            raise
        return response

    def close(self) -> None:
        for transport in self.pool.active():
            transport.close()
        self.pool.clear()


class AsyncOutboundHTTPTransport(httpx2.AsyncBaseTransport):
    """Validate and route every asynchronous HTTPX2 request hop."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.pool = OutboundTransportPool(
            transport,
            lambda proxy: httpx2.AsyncHTTPTransport(proxy=proxy, trust_env=True),
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        outbound = _prepare_outbound_request(request)
        connection_addresses = await _validate_async_outbound_request(outbound)
        trace = trace_http_request(request)
        span = trace.__enter__()  # ruff: ignore[unnecessary-dunder-call]
        response: httpx2.Response | None = None
        try:
            routes = _route_outbound_request(
                self.pool,
                request,
                connection_addresses,
                proxy=outbound.proxy,
            )
            response = await _send_async_request_with_fallback(routes)
            _validate_transport_response(
                response,
                request=request,
                span=span,
                validators=outbound.validators,
                used_proxy=outbound.used_proxy,
            )
            response.stream = TracedAsyncStream(
                cast("httpx2.AsyncByteStream", response.stream), trace
            )
        except BaseException as error:
            try:
                if response is not None:
                    await response.aclose()
            finally:
                trace.__exit__(type(error), error, error.__traceback__)
            raise
        return response

    async def aclose(self) -> None:
        for transport in self.pool.active():
            await transport.aclose()
        self.pool.clear()


def _build_client_request(
    client: httpx2.Client | httpx2.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    timeout: float,
    validators: RedirectValidators | None,
    kwargs: dict[str, Any],
) -> tuple[httpx2.Request, AuthTypes | None]:
    request_kwargs = _normalize_request_kwargs(kwargs)
    request_auth = request_kwargs.pop("auth", None)
    extensions = dict(request_kwargs.pop("extensions", {}) or {})
    extensions[VALIDATORS_REQUEST_EXTENSION] = validators
    request = client.build_request(
        method,
        url,
        headers=_prepare_headers(headers),
        timeout=timeout,
        extensions=extensions,
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


def _send_with_redirects(
    client: httpx2.Client,
    request: httpx2.Request,
    *,
    auth: AuthTypes | None,
    max_redirects: int,
) -> httpx2.Response:
    history: list[httpx2.Response] = []
    while True:
        response = client.send(
            request,
            stream=True,
            auth=auth,
            follow_redirects=False,
        )
        try:
            next_request = _next_streaming_redirect(response, history, max_redirects)
        except BaseException:
            response.close()
            raise
        if next_request is None:
            return response
        response.close()
        request = next_request
        auth = None


async def _async_send_with_redirects(
    client: httpx2.AsyncClient,
    request: httpx2.Request,
    *,
    auth: AuthTypes | None,
    max_redirects: int,
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
            next_request = _next_streaming_redirect(response, history, max_redirects)
        except BaseException:
            await response.aclose()
            raise
        if next_request is None:
            return response
        await response.aclose()
        request = next_request
        auth = None


class HTTPClient:
    """Synchronous HTTPX2 client using Weblate's outbound transport."""

    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        self.client = httpx2.Client(
            transport=OutboundHTTPTransport(transport),
            trust_env=False,
            follow_redirects=False,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

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
        request, request_auth = _build_client_request(
            self.client,
            method,
            url,
            headers=headers,
            timeout=timeout,
            validators=validators,
            kwargs=kwargs,
        )
        if allow_redirects:
            response = _send_with_redirects(
                self.client,
                request,
                auth=request_auth,
                max_redirects=max_redirects,
            )
            if stream:
                return response
            try:
                response.read()
            except BaseException:
                response.close()
                raise
            return response
        return self.client.send(
            request,
            stream=stream,
            auth=request_auth,
            follow_redirects=False,
        )


class AsyncHTTPClient:
    """Asynchronous HTTPX2 client using Weblate's outbound transport."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.client = httpx2.AsyncClient(
            transport=AsyncOutboundHTTPTransport(transport),
            trust_env=False,
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.aclose()

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
        request, request_auth = _build_client_request(
            self.client,
            method,
            url,
            headers=headers,
            timeout=timeout,
            validators=validators,
            kwargs=kwargs,
        )
        if allow_redirects:
            response = await _async_send_with_redirects(
                self.client,
                request,
                auth=request_auth,
                max_redirects=max_redirects,
            )
            if stream:
                return response
            try:
                await response.aread()
            except BaseException:
                await response.aclose()
                raise
            return response
        return await self.client.send(
            request,
            stream=stream,
            auth=request_auth,
            follow_redirects=False,
        )


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
