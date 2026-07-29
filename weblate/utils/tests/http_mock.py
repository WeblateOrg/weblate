# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small responses-compatible HTTPX2 mock used by the existing test suite."""

from __future__ import annotations

import json as json_module
import re
from collections import UserList
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

GET = "GET"
POST = "POST"
PUT = "PUT"
PATCH = "PATCH"
DELETE = "DELETE"
HEAD = "HEAD"
OPTIONS = "OPTIONS"

type ResponseHeaders = dict[str, str] | list[tuple[str, str]] | None


class Calls(UserList):
    def reset(self) -> None:
        self.clear()


class PreparedRequest:
    """Requests-shaped view of an HTTPX2 request for legacy callbacks."""

    def __init__(self, request: httpx2.Request) -> None:
        self._request = request
        self.extensions = dict(request.extensions)
        request_url = request.extensions.get(
            ORIGINAL_URL_REQUEST_EXTENSION, request.url
        )
        self.method = request.method
        self.url = str(request_url.copy_with(fragment=None))
        self.transport_url = str(request.url.copy_with(fragment=None))
        self.headers = request.headers
        self.body = request.content or None
        self.path_url = request_url.raw_path.decode("ascii")


@dataclass
class Call:
    request: PreparedRequest
    response: httpx2.Response | BaseException


@dataclass
class Registration:
    method: str
    url: str | re.Pattern[str]
    body: str | bytes | BaseException = b""
    json: object | None = None
    status: int = 200
    headers: ResponseHeaders = None
    callback: (
        Callable[[PreparedRequest], tuple[int, ResponseHeaders, object]] | None
    ) = None
    match: list[Callable[[PreparedRequest], tuple[bool, str]]] = field(
        default_factory=list
    )
    calls: Calls = field(default_factory=Calls)

    def matches(self, request: PreparedRequest) -> bool:
        if self.method != request.method:
            return False
        if isinstance(self.url, re.Pattern):
            if self.url.search(request.url) is None:
                return False
        elif self.url != request.url:
            registered = urlsplit(self.url)
            requested = urlsplit(request.url)
            if registered.query or self.url != urlunsplit(
                (requested.scheme, requested.netloc, requested.path, "", "")
            ):
                return False
        return all(matcher(request)[0] for matcher in self.match)

    def respond(
        self, request: PreparedRequest, original: httpx2.Request
    ) -> httpx2.Response:
        try:
            if self.callback is not None:
                status, headers, body = self.callback(request)
                response = _build_response(
                    original,
                    status=status,
                    headers=headers,
                    body=body,
                )
            else:
                response = _build_response(
                    original,
                    status=self.status,
                    headers=self.headers,
                    body=self.body,
                    json=self.json,
                )
        except Exception as error:
            call = Call(request=request, response=error)
            calls.append(call)
            self.calls.append(call)
            raise
        call = Call(request=request, response=response)
        calls.append(call)
        self.calls.append(call)
        return response


calls = Calls()
_registrations: list[Registration] = []


class Matchers:
    @staticmethod
    def json_params_matcher(expected: object, *, strict_match: bool = True):
        def match(request: PreparedRequest) -> tuple[bool, str]:
            try:
                actual = json_module.loads(request.body or b"null")
            except (json_module.JSONDecodeError, UnicodeDecodeError) as error:
                return False, f"request body is not valid JSON: {error}"
            if (
                not strict_match
                and isinstance(actual, dict)
                and isinstance(expected, dict)
            ):
                actual = _filter_mapping(actual, expected)
            return (
                actual == expected,
                f"JSON body {actual!r} does not match {expected!r}",
            )

        return match

    @staticmethod
    def header_matcher(expected: dict[str, str]):
        def match(request: PreparedRequest) -> tuple[bool, str]:
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


matchers = Matchers()


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
    status: int,
    headers: ResponseHeaders = None,
    body: object = b"",
    json: object | None = None,
) -> httpx2.Response:
    if isinstance(body, BaseException):
        raise body
    if json is not None:
        response = httpx2.Response(
            status,
            headers=headers,
            json=json,
            request=request,
        )
    elif isinstance(body, bytes):
        response = httpx2.Response(
            status,
            headers=headers,
            content=body,
            request=request,
        )
    elif body is not None:
        response = httpx2.Response(
            status,
            headers=headers,
            text=str(body),
            request=request,
        )
    else:
        response = httpx2.Response(status, headers=headers, request=request)
    setattr(response, PEER_IP_RESPONSE_ATTR, "93.184.216.34")
    return response


def _handler(request: httpx2.Request) -> httpx2.Response:
    prepared = PreparedRequest(request)
    matches = [
        (index, registration)
        for index, registration in enumerate(_registrations)
        if registration.matches(prepared)
    ]
    if not matches:
        msg = f"Connection refused: {request.method} {request.url}"
        error = httpx2.ConnectError(msg, request=request)
        calls.append(Call(request=prepared, response=error))
        raise error
    index, registration = matches[0]
    if len(matches) > 1:
        _registrations.pop(index)
        if registration.calls:
            registration = matches[1][1]
    return registration.respond(prepared, request)


def reset() -> None:
    _registrations.clear()
    calls.reset()


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


def add(
    method: str,
    url: str | re.Pattern[str],
    body: str | bytes | BaseException = b"",
    *,
    json: object | None = None,
    status: int = 200,
    headers: dict[str, str] | list[tuple[str, str]] | None = None,
    content_type: str | None = None,
    match: list[Callable[[PreparedRequest], tuple[bool, str]]] | None = None,
    **_kwargs,
) -> Registration:
    result_headers = dict(headers or {})
    if content_type is not None:
        result_headers["Content-Type"] = content_type
    registration = Registration(
        method=method.upper(),
        url=url,
        body=body,
        json=json,
        status=status,
        headers=result_headers,
        match=list(match or ()),
    )
    _registrations.append(registration)
    return registration


def add_callback(
    method: str,
    url: str | re.Pattern[str],
    *,
    callback,
    match=None,
    **kwargs,
) -> Registration:
    registration = add(method, url, match=match, **kwargs)
    registration.callback = callback
    return registration


def remove(method: str, url: str | re.Pattern[str]) -> None:
    _registrations[:] = [
        registration
        for registration in _registrations
        if not (registration.method == method.upper() and registration.url == url)
    ]


def replace(method: str, url: str | re.Pattern[str], **kwargs) -> Registration:
    remove(method, url)
    return add(method, url, **kwargs)


def assert_call_count(url: str, count: int) -> None:
    actual = sum(call.request.url == url for call in calls)
    if actual != count:
        msg = f"Expected {url!r} to be called {count} times, called {actual} times."
        raise AssertionError(msg)


def get(url, **kwargs) -> Registration:
    return add(GET, url, **kwargs)


def post(url, **kwargs) -> Registration:
    return add(POST, url, **kwargs)


def delete(*args, **kwargs):
    if len(args) == 2:
        return remove(args[0], args[1])
    return add(DELETE, args[0], **kwargs)
