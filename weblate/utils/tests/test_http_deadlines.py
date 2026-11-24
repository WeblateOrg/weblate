# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""HTTP deadlines cover the entire asynchronous exchange and sync bridges."""

from __future__ import annotations

import asyncio
import socket
from threading import Event, Timer
from time import monotonic
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx2
from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.utils.requests import (
    RuntimeRedirectValidators,
    async_fetch_url,
    async_open_url,
    fetch_restricted_asset_url,
    fetch_url,
    fetch_validated_url,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class SlowBody(httpx2.AsyncByteStream):
    def __init__(self, events: list[str], delay: float = 0.01) -> None:
        self.events = events
        self.delay = delay

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index in range(100):
            if index:
                await asyncio.sleep(self.delay)
            self.events.append("chunk")
            yield b"x"

    async def aclose(self) -> None:
        self.events.append("body-closed")


class DeadlineTransport(httpx2.MockTransport):
    async def aclose(self) -> None:
        await super().aclose()
        self.closed = True


class HTTPDeadlineTest(SimpleTestCase):
    def test_sync_and_async_deadline_stops_continuous_body(self) -> None:
        for synchronous in (False, True):
            with self.subTest(synchronous=synchronous):
                events: list[str] = []
                transport = DeadlineTransport(
                    lambda _request, events=events: httpx2.Response(
                        200, stream=SlowBody(events)
                    )
                )
                with (
                    patch(
                        "weblate.utils.requests._TEST_TRANSPORT.transport", transport
                    ),
                    self.assertRaises(httpx2.TimeoutException) as raised,
                ):
                    if synchronous:
                        fetch_url("GET", "https://example.com/data", timeout=0.2)
                    else:
                        asyncio.run(
                            async_fetch_url(
                                "GET", "https://example.com/data", timeout=0.2
                            )
                        )
                self.assertEqual(
                    str(raised.exception.request.url), "https://example.com/data"
                )
                self.assertIn("chunk", events)
                self.assertEqual(events[-1], "body-closed")
                self.assertTrue(transport.closed)

    def test_stalled_headers_are_cancelled(self) -> None:
        events: list[str] = []

        async def headers(_request: httpx2.Request) -> httpx2.Response:
            try:
                await asyncio.sleep(10)
            finally:
                events.append("headers-cancelled")
            self.fail("Headers should have been cancelled")

        transport = DeadlineTransport(headers)
        with (
            patch("weblate.utils.requests._TEST_TRANSPORT.transport", transport),
            self.assertRaises(httpx2.TimeoutException),
        ):
            fetch_url("GET", "https://example.com/", timeout=0.05)
        self.assertEqual(events, ["headers-cancelled"])
        self.assertTrue(transport.closed)

    def test_redirects_share_one_budget(self) -> None:
        calls: list[str] = []

        async def redirect(request: httpx2.Request) -> httpx2.Response:
            calls.append(request.url.path)
            await asyncio.sleep(0.12)
            return httpx2.Response(302, headers={"Location": "/next"})

        transport = DeadlineTransport(redirect)
        with (
            patch("weblate.utils.requests._TEST_TRANSPORT.transport", transport),
            self.assertRaises(httpx2.TimeoutException),
        ):
            fetch_url("GET", "https://example.com/", timeout=0.2)
        self.assertEqual(calls, ["/", "/next"])
        self.assertTrue(transport.closed)

    def test_headers_and_body_share_one_budget(self) -> None:
        events: list[str] = []

        async def headers(_request: httpx2.Request) -> httpx2.Response:
            await asyncio.sleep(0.12)
            return httpx2.Response(200, stream=SlowBody(events, delay=0.12))

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                DeadlineTransport(headers),
            ),
            self.assertRaises(httpx2.TimeoutException),
        ):
            fetch_url("GET", "https://example.com/", timeout=0.2)
        self.assertEqual(events, ["chunk", "body-closed"])

    def test_authentication_round_trips_share_one_budget(self) -> None:
        calls: list[str] = []

        async def challenge(request: httpx2.Request) -> httpx2.Response:
            calls.append(request.headers.get("Authorization", ""))
            await asyncio.sleep(0.12)
            if len(calls) == 1:
                return httpx2.Response(
                    401,
                    headers={
                        "WWW-Authenticate": 'Digest realm="test", nonce="value", qop="auth"'
                    },
                )
            return httpx2.Response(200, content=b"ok")

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                DeadlineTransport(challenge),
            ),
            self.assertRaises(httpx2.TimeoutException),
        ):
            fetch_url(
                "GET",
                "https://example.com/",
                timeout=0.2,
                auth=httpx2.DigestAuth("user", "secret"),
            )
        self.assertEqual(calls[0], "")
        self.assertTrue(calls[1].startswith("Digest "))

    def test_address_fallback_shares_total_budget(self) -> None:
        addresses: list[str] = []

        async def connect(request: httpx2.Request) -> httpx2.Response:
            addresses.append(request.url.host)
            await asyncio.sleep(0.12)
            msg = "Try another address"
            raise httpx2.ConnectError(msg, request=request)

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                DeadlineTransport(connect),
            ),
            patch.object(
                RuntimeRedirectValidators,
                "validate_async_request_url",
                return_value=("93.184.216.34", "93.184.216.35"),
            ),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaises(httpx2.TimeoutException),
        ):
            fetch_validated_url("GET", "https://example.com/", timeout=0.2)
        self.assertEqual(addresses, ["93.184.216.34", "93.184.216.35"])

    def test_external_cancellation_is_preserved(self) -> None:
        events: list[str] = []
        transport = DeadlineTransport(
            lambda _request: httpx2.Response(200, stream=SlowBody(events))
        )

        async def cancel_request() -> None:
            task = asyncio.create_task(
                async_fetch_url("GET", "https://example.com/", timeout=10)
            )
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with patch("weblate.utils.requests._TEST_TRANSPORT.transport", transport):
            asyncio.run(cancel_request())
        self.assertEqual(events[-1], "body-closed")
        self.assertTrue(transport.closed)

    def test_unrelated_timeout_error_is_preserved(self) -> None:
        error = TimeoutError("Consumer's own timeout")

        def handler(_request: httpx2.Request) -> httpx2.Response:
            raise error

        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                DeadlineTransport(handler),
            ),
            self.assertRaises(TimeoutError) as raised,
        ):
            fetch_url("GET", "https://example.com/", timeout=10)
        self.assertIs(raised.exception, error)

    def test_configured_and_disabled_timeouts(self) -> None:
        def inspect(request: httpx2.Request) -> httpx2.Response:
            budget = request.extensions["timeout"]["read"]
            return httpx2.Response(200, json={"budget": budget})

        with patch(
            "weblate.utils.requests._TEST_TRANSPORT.transport",
            DeadlineTransport(inspect),
        ):
            for value in (None, 120, 360, httpx2.Timeout(10, read=20)):
                with self.subTest(value=value):
                    response = fetch_url("GET", "https://example.com/", timeout=value)
                    self.assertEqual(
                        response.json()["budget"],
                        value.read if isinstance(value, httpx2.Timeout) else value,
                    )
            self.assertEqual(
                fetch_url("GET", "https://example.com/").json()["budget"], 5
            )

    def test_asset_status_rejection_precedes_body(self) -> None:
        events: list[str] = []
        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                DeadlineTransport(
                    lambda _request: httpx2.Response(500, stream=SlowBody(events))
                ),
            ),
            self.assertRaisesMessage(ValidationError, "Unable to download asset"),
        ):
            fetch_restricted_asset_url(
                "GET", "https://example.com/", allow_private_targets=True
            )
        self.assertEqual(events, ["body-closed"])

    def test_header_only_probe_never_reads_body(self) -> None:
        events: list[str] = []

        async def probe() -> int:
            async with async_open_url("GET", "https://example.com/") as response:
                return response.status_code

        with patch(
            "weblate.utils.requests._TEST_TRANSPORT.transport",
            DeadlineTransport(
                lambda _request: httpx2.Response(200, stream=SlowBody(events))
            ),
        ):
            self.assertEqual(async_to_sync(probe)(), 200)
        self.assertEqual(events, ["body-closed"])

    def test_dns_completion_can_delay_sync_return(self) -> None:
        release = Event()
        finished = Event()
        started = monotonic()

        def resolve(
            *args: object, **kwargs: object
        ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            release.wait(1)
            finished.set()
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        timer = Timer(0.3, release.set)
        timer.start()
        try:
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("weblate.utils.outbound.socket.getaddrinfo", side_effect=resolve),
                self.assertRaises(httpx2.TimeoutException),
            ):
                fetch_validated_url("GET", "https://example.com/", timeout=0.05)
            self.assertTrue(finished.is_set())
            self.assertGreaterEqual(monotonic() - started, 0.2)
        finally:
            release.set()
            timer.join()

    def test_real_network_cancellation_closes_connection(self) -> None:
        async def exchange(send_headers: bool) -> None:
            closed = asyncio.Event()

            async def serve(
                reader: asyncio.StreamReader, writer: asyncio.StreamWriter
            ) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    if send_headers:
                        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nx")
                        await writer.drain()
                    await reader.read()
                    closed.set()
                finally:
                    writer.close()
                    await writer.wait_closed()

            async with await asyncio.start_server(serve, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                with self.assertRaises(httpx2.TimeoutException):
                    await async_fetch_url(
                        "GET", f"http://127.0.0.1:{port}/", timeout=0.5
                    )
                await asyncio.wait_for(closed.wait(), 1)

        with (
            patch("weblate.utils.requests._TEST_TRANSPORT.transport", None),
            patch.dict("os.environ", {}, clear=True),
        ):
            for send_headers in (False, True):
                with self.subTest(send_headers=send_headers):
                    asyncio.run(exchange(send_headers))
