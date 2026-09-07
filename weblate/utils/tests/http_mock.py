# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""HTTPX2 mock transport helpers for the test suite."""

from __future__ import annotations

import json as json_module
import re
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import httpx2

from weblate.utils.requests import (
    ORIGINAL_URL_REQUEST_EXTENSION,
    PEER_IP_RESPONSE_ATTR,
    set_test_transport,
)

if TYPE_CHECKING:
    from collections.abc import Callable

type ResponseHeaders = dict[str, str] | list[tuple[str, str]] | None
type RequestMatcher = Callable[[httpx2.Request], tuple[bool, str]]
type ResponseCallback = Callable[[httpx2.Request], httpx2.Response]

_TRANSPORT_URL_REQUEST_EXTENSION = "weblate.transport_url"


class _Unset:
    pass


_UNSET = _Unset()


@dataclass
class Call:
    request: httpx2.Request
    response: httpx2.Response | BaseException


@dataclass
class Route:
    method: str
    url: str | re.Pattern[str]
    status_code: int = 200
    headers: ResponseHeaders = None
    content: bytes | None = None
    text: str | None = None
    json: object = _UNSET
    callback: ResponseCallback | None = None
    exception: BaseException | None = None
    match: list[RequestMatcher] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    def matches(self, request: httpx2.Request) -> bool:
        request_url = str(request.url)
        if self.method != request.method:
            return False
        if isinstance(self.url, re.Pattern):
            if self.url.search(request_url) is None:
                return False
        elif self.url != request_url:
            registered = urlsplit(self.url)
            requested = urlsplit(request_url)
            if registered.query or self.url != urlunsplit(
                (requested.scheme, requested.netloc, requested.path, "", "")
            ):
                return False
        return all(matcher(request)[0] for matcher in self.match)

    def respond(
        self, request: httpx2.Request, transport_request: httpx2.Request
    ) -> httpx2.Response:
        try:
            response = self._get_response(request, transport_request)
        except BaseException as error:
            call = Call(request=request, response=error)
            calls.append(call)
            self.calls.append(call)
            raise
        call = Call(request=request, response=response)
        calls.append(call)
        self.calls.append(call)
        return response

    def _get_response(
        self, request: httpx2.Request, transport_request: httpx2.Request
    ) -> httpx2.Response:
        if self.exception is not None:
            raise self.exception
        if self.callback is not None:
            response = self.callback(request)
            if not isinstance(response, httpx2.Response):
                msg = "HTTP mock callbacks must return an httpx2.Response"
                raise TypeError(msg)
        else:
            response = _build_response(
                transport_request,
                status_code=self.status_code,
                headers=self.headers,
                content=self.content,
                text=self.text,
                json=self.json,
            )
        response.request = transport_request
        setattr(response, PEER_IP_RESPONSE_ATTR, "93.184.216.34")
        return response


calls: list[Call] = []
_routes: list[Route] = []


def json_params_matcher(
    expected: object, *, strict_match: bool = True
) -> RequestMatcher:
    def match(request: httpx2.Request) -> tuple[bool, str]:
        try:
            actual = json_module.loads(request.content or b"null")
        except (json_module.JSONDecodeError, UnicodeDecodeError) as error:
            return False, f"request body is not valid JSON: {error}"
        if not strict_match and isinstance(actual, dict) and isinstance(expected, dict):
            actual = _filter_mapping(actual, expected)
        return (
            actual == expected,
            f"JSON body {actual!r} does not match {expected!r}",
        )

    return match


def header_matcher(expected: dict[str, str]) -> RequestMatcher:
    def match(request: httpx2.Request) -> tuple[bool, str]:
        actual = {
            name: request.headers.get(name)
            for name in expected
            if name in request.headers
        }
        return (
            actual == expected,
            f"headers {actual!r} do not match {expected!r}",
        )

    return match


def get_transport_url(request: httpx2.Request) -> httpx2.URL:
    """Return the URL passed to the transport after address pinning."""
    return request.extensions[_TRANSPORT_URL_REQUEST_EXTENSION]


def _filter_mapping(actual: dict, expected: dict) -> dict:
    result = {}
    for key, value in actual.items():
        if key not in expected:
            continue
        if isinstance(value, dict) and isinstance(expected[key], dict):
            value = _filter_mapping(value, expected[key])
        result[key] = value
    return result


def _build_response(
    request: httpx2.Request,
    *,
    status_code: int,
    headers: ResponseHeaders,
    content: bytes | None,
    text: str | None,
    json: object,
) -> httpx2.Response:
    if json is not _UNSET:
        if json is None:
            result_headers = httpx2.Headers(headers)
            result_headers.setdefault("Content-Type", "application/json")
            return httpx2.Response(
                status_code,
                headers=result_headers,
                content=b"null",
                request=request,
            )
        return httpx2.Response(
            status_code,
            headers=headers,
            json=json,
            request=request,
        )
    if text is not None:
        return httpx2.Response(
            status_code,
            headers=headers,
            text=text,
            request=request,
        )
    return httpx2.Response(
        status_code,
        headers=headers,
        content=content,
        request=request,
    )


def _logical_request(request: httpx2.Request) -> httpx2.Request:
    transport_url = request.url.copy_with(fragment=None)
    logical_url = request.extensions.get(
        ORIGINAL_URL_REQUEST_EXTENSION, request.url
    ).copy_with(fragment=None)
    extensions = dict(request.extensions)
    extensions[_TRANSPORT_URL_REQUEST_EXTENSION] = transport_url
    return httpx2.Request(
        request.method,
        logical_url,
        headers=request.headers,
        content=request.content,
        extensions=extensions,
    )


def _handler(request: httpx2.Request) -> httpx2.Response:
    logical_request = _logical_request(request)
    matches = [
        (index, route)
        for index, route in enumerate(_routes)
        if route.matches(logical_request)
    ]
    if not matches:
        msg = f"Connection refused: {request.method} {request.url}"
        error = httpx2.ConnectError(msg, request=request)
        calls.append(Call(request=logical_request, response=error))
        raise error
    index, route = matches[0]
    if len(matches) > 1:
        _routes.pop(index)
        if route.calls:
            route = matches[1][1]
    return route.respond(logical_request, request)


def reset() -> None:
    _routes.clear()
    calls.clear()


def activate(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        reset()
        set_test_transport(httpx2.MockTransport(_handler))
        try:
            return function(*args, **kwargs)
        finally:
            set_test_transport(None)
            reset()

    @wraps(function)
    async def async_wrapper(*args, **kwargs):
        reset()
        set_test_transport(httpx2.MockTransport(_handler))
        try:
            return await function(*args, **kwargs)
        finally:
            set_test_transport(None)
            reset()

    return async_wrapper if function.__code__.co_flags & 0x80 else wrapper


def _validate_response_body(
    *, content: bytes | None, text: str | None, json: object
) -> None:
    supplied = sum((content is not None, text is not None, json is not _UNSET))
    if supplied > 1:
        msg = "Only one of content, text, or json can be supplied"
        raise TypeError(msg)


def register(
    method: str,
    url: str | re.Pattern[str],
    *,
    status_code: int = 200,
    headers: ResponseHeaders = None,
    content: bytes | None = None,
    text: str | None = None,
    json: object = _UNSET,
    match: list[RequestMatcher] | None = None,
) -> Route:
    _validate_response_body(content=content, text=text, json=json)
    route = Route(
        method=method.upper(),
        url=url,
        status_code=status_code,
        headers=headers,
        content=content,
        text=text,
        json=json,
        match=list(match or ()),
    )
    _routes.append(route)
    return route


def register_callback(
    method: str,
    url: str | re.Pattern[str],
    callback: ResponseCallback,
    *,
    match: list[RequestMatcher] | None = None,
) -> Route:
    route = Route(
        method=method.upper(),
        url=url,
        callback=callback,
        match=list(match or ()),
    )
    _routes.append(route)
    return route


def register_exception(
    method: str,
    url: str | re.Pattern[str],
    exception: BaseException,
    *,
    match: list[RequestMatcher] | None = None,
) -> Route:
    route = Route(
        method=method.upper(),
        url=url,
        exception=exception,
        match=list(match or ()),
    )
    _routes.append(route)
    return route


def unregister(method: str, url: str | re.Pattern[str]) -> None:
    _routes[:] = [
        route
        for route in _routes
        if not (route.method == method.upper() and route.url == url)
    ]


def replace(
    method: str,
    url: str | re.Pattern[str],
    *,
    status_code: int = 200,
    headers: ResponseHeaders = None,
    content: bytes | None = None,
    text: str | None = None,
    json: object = _UNSET,
    match: list[RequestMatcher] | None = None,
) -> Route:
    unregister(method, url)
    return register(
        method,
        url,
        status_code=status_code,
        headers=headers,
        content=content,
        text=text,
        json=json,
        match=match,
    )


def assert_call_count(url: str, count: int) -> None:
    actual = sum(str(call.request.url) == url for call in calls)
    if actual != count:
        msg = f"Expected {url!r} to be called {count} times, called {actual} times."
        raise AssertionError(msg)
