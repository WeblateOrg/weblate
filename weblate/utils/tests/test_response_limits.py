# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import gzip
import json
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import httpx2
from django.test import SimpleTestCase, override_settings

from weblate.addons.tasks import read_cdn_file
from weblate.machinery.libretranslate import LibreTranslateTranslation
from weblate.screenshots.ocr import download_tesseract_data
from weblate.trans.models import Project
from weblate.utils.requests import (
    DEFAULT_RESPONSE_SIZE,
    MACHINERY_RESPONSE_SIZE,
    PEER_IP_RESPONSE_ATTR,
    ResponseTooLarge,
    async_fetch_url,
    async_fetch_validated_url,
    fetch_url,
    fetch_validated_url,
)
from weblate.utils.tests.network import mock_dns
from weblate.vcs.github import GitHubAppCredentials, get_authenticated_github_user

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from weblate.machinery.types import SettingsDict


class ChunkStream(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.consumed = 0
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self:
            yield chunk

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.close()


class ResponseLimitsTest(SimpleTestCase):
    url = "https://example.com/data"

    @staticmethod
    def make_transport(
        stream: ChunkStream, headers: dict[str, str] | None = None
    ) -> httpx2.MockTransport:
        def handle(_request: httpx2.Request) -> httpx2.Response:
            response = httpx2.Response(
                200, stream=stream, headers=headers, extensions={"marker": "retained"}
            )
            setattr(response, PEER_IP_RESPONSE_ATTR, "93.184.216.34")
            return response

        return httpx2.MockTransport(handle)

    def fetch(self, mode: str, limit: int) -> httpx2.Response:
        if mode == "sync":
            return fetch_url("get", self.url, max_response_size=limit)
        if mode == "async":
            return asyncio.run(
                async_fetch_url("get", self.url, max_response_size=limit)
            )
        if mode == "validated":
            return fetch_validated_url(
                "get",
                self.url,
                max_response_size=limit,
                private_allowlist=("example.com",),
            )
        return asyncio.run(
            async_fetch_validated_url(
                "get",
                self.url,
                max_response_size=limit,
                private_allowlist=("example.com",),
            )
        )

    def test_exact_limit_and_metadata(self) -> None:
        body = '{"text":"čeština"}'.encode()
        for mode in ("sync", "async", "validated", "async_validated"):
            stream = ChunkStream([gzip.compress(body)])
            headers = {
                "Content-Encoding": "gzip",
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(stream.chunks[0])),
                "Set-Cookie": "name=value",
            }
            with (
                self.subTest(mode=mode),
                patch(
                    "weblate.utils.requests._TEST_TRANSPORT.transport",
                    self.make_transport(stream, headers=headers),
                ),
            ):
                response = self.fetch(mode, len(body))
                self.assertEqual(response.content, body)
                self.assertEqual(response.json(), {"text": "čeština"})
                self.assertEqual(str(response.url), self.url)
                self.assertEqual(
                    dict(response.headers),
                    {key.lower(): value for key, value in headers.items()},
                )
                self.assertEqual(response.cookies["name"], "value")
                self.assertEqual(response.extensions["marker"], "retained")
                self.assertGreaterEqual(response.elapsed.total_seconds(), 0)
                self.assertTrue(response.is_closed)
                self.assertTrue(stream.closed)

    def test_excess_content_stops_reading_and_closes(self) -> None:
        for mode in ("sync", "async", "validated", "async_validated"):
            for headers in ({}, {"Content-Length": "1"}):
                stream = ChunkStream([b"1234", b"5678", b"9", b"never read"])
                with (
                    self.subTest(mode=mode, headers=headers),
                    patch(
                        "weblate.utils.requests._TEST_TRANSPORT.transport",
                        self.make_transport(stream, headers=headers),
                    ),
                ):
                    with self.assertRaises(ResponseTooLarge) as raised:
                        self.fetch(mode, 8)
                    self.assertEqual(str(raised.exception.request.url), self.url)
                    self.assertEqual(stream.consumed, 3)
                    self.assertTrue(stream.closed)

    def test_compression_expansion_is_counted(self) -> None:
        body = b"a" * 4096
        for mode in ("sync", "async"):
            for encoding, compressed in (
                ("gzip", gzip.compress(body)),
                ("deflate", zlib.compress(body)),
            ):
                stream = ChunkStream([compressed, b"never read"])
                with (
                    self.subTest(mode=mode, encoding=encoding),
                    patch(
                        "weblate.utils.requests._TEST_TRANSPORT.transport",
                        self.make_transport(
                            stream, headers={"Content-Encoding": encoding}
                        ),
                    ),
                ):
                    with self.assertRaises(ResponseTooLarge):
                        self.fetch(mode, 1024)
                    self.assertEqual(stream.consumed, 1)
                    self.assertTrue(stream.closed)

    def test_default_budget(self) -> None:
        stream = ChunkStream([b"x" * DEFAULT_RESPONSE_SIZE, b"x"])
        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                self.make_transport(stream),
            ),
            self.assertRaises(ResponseTooLarge),
        ):
            fetch_url("get", self.url)
        self.assertTrue(stream.closed)

    def test_prebuffered_response_is_checked(self) -> None:
        with (
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                httpx2.MockTransport(
                    lambda _request: httpx2.Response(200, content=b"12345")
                ),
            ),
            self.assertRaises(ResponseTooLarge),
        ):
            self.fetch("sync", 4)

    def test_redirect_and_error_response_metadata(self) -> None:
        def handle(request: httpx2.Request) -> httpx2.Response:
            if request.url.path == "/data":
                return httpx2.Response(
                    302, headers={"Location": "/final"}, stream=ChunkStream([b"unused"])
                )
            return httpx2.Response(
                503, headers={"Retry-After": "60"}, stream=ChunkStream([b"error"])
            )

        with patch(
            "weblate.utils.requests._TEST_TRANSPORT.transport",
            httpx2.MockTransport(handle),
        ):
            response = fetch_url("get", self.url, raise_for_status=False)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.text, "error")
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(len(response.history), 1)
        self.assertTrue(response.history[0].is_closed)
        self.assertEqual(str(response.url), "https://example.com/final")
        with self.assertRaises(httpx2.HTTPStatusError) as raised:
            response.raise_for_status()
        self.assertIs(raised.exception.response, response)

    @override_settings(ALLOWED_MACHINERY_DOMAINS=["example.com"])
    def test_machinery_budget_for_site_and_project_services(self) -> None:
        configurations: list[SettingsDict] = [
            {"url": "https://example.com/", "key": ""},
            {
                "url": "https://example.com/",
                "key": "",
                "_project": Project(name="Test", slug="test"),
            },
        ]
        for configuration in configurations:
            machine = LibreTranslateTranslation(configuration)
            for mode in ("sync", "async"):
                stream = ChunkStream([b"x" * MACHINERY_RESPONSE_SIZE, b"x"])
                with (
                    self.subTest(project="_project" in configuration, mode=mode),
                    patch(
                        "weblate.utils.requests._TEST_TRANSPORT.transport",
                        self.make_transport(stream),
                    ),
                    self.assertRaises(ResponseTooLarge),
                ):
                    if mode == "sync":
                        machine.request("get", self.url)
                    else:
                        asyncio.run(machine.arequest("get", self.url))
                self.assertTrue(stream.closed)

    @override_settings(
        ALLOWED_ASSET_SIZE=8,
        ALLOWED_ASSET_DOMAINS=["example.com"],
        ASSET_PRIVATE_ALLOWLIST=["example.com"],
    )
    def test_cdn_respects_asset_budget(self) -> None:
        for size in (8, 9):
            stream = ChunkStream([b"x" * size])
            with (
                self.subTest(size=size),
                patch(
                    "weblate.utils.requests._TEST_TRANSPORT.transport",
                    self.make_transport(stream),
                ),
            ):
                if size == 8:
                    self.assertEqual(read_cdn_file(Mock(), self.url), "x" * size)
                else:
                    with self.assertRaises(ResponseTooLarge):
                        read_cdn_file(Mock(), self.url)
                self.assertTrue(stream.closed)

    def test_oversized_ocr_data_preserves_existing_file(self) -> None:
        stream = ChunkStream([b"x" * 1025])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "osd.traineddata"
            target.write_bytes(b"original")
            with (
                patch("weblate.screenshots.ocr.TESSERACT_RESPONSE_SIZE", 1024),
                patch(
                    "weblate.utils.requests._TEST_TRANSPORT.transport",
                    self.make_transport(stream),
                ),
                self.assertRaises(ResponseTooLarge),
            ):
                download_tesseract_data(self.url, str(target))
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [target])
        self.assertTrue(stream.closed)

    @override_settings(
        VCS_RESTRICT_PRIVATE=True,
        VCS_ALLOW_HOSTS=[],
        VCS_PRIVATE_ALLOWLIST=[],
    )
    @mock_dns("api.github.com")
    def test_github_json_uses_larger_budget(self) -> None:
        body = json.dumps(
            {"login": "test", "details": "x" * DEFAULT_RESPONSE_SIZE}
        ).encode()
        stream = ChunkStream([body])
        with (
            patch("weblate.utils.requests.get_environment_proxy", return_value=None),
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                self.make_transport(stream),
            ),
        ):
            data = asyncio.run(
                get_authenticated_github_user(
                    GitHubAppCredentials(hostname="github.com"), "token"
                )
            )
        self.assertEqual(data["login"], "test")
        self.assertEqual(len(data["details"]), DEFAULT_RESPONSE_SIZE)
        self.assertTrue(stream.closed)
