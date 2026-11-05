# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from django.test import RequestFactory

from weblate.utils.views import get_page_limit, zip_download

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIRequest


def fake_request(page: str, limit: str) -> WSGIRequest:
    return RequestFactory().get("/", {"page": page, "limit": limit})


class PageLimitTest(TestCase):
    def test_defaults(self) -> None:
        self.assertEqual((1, 42), get_page_limit(fake_request("x", "x"), 42))

    def test_negative(self) -> None:
        self.assertEqual((1, 10), get_page_limit(fake_request("-1", "-1"), 42))

    def test_valid(self) -> None:
        self.assertEqual((33, 66), get_page_limit(fake_request("33", "66"), 42))


class ZipDownloadTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        # These direct helper calls have no request or database lifecycle to finish.
        self.enterContext(patch("django.http.response.signals.request_finished.send"))

    def test_completed_archive_headers_and_contents(self) -> None:
        content = b"translation content" * 1000
        response = zip_download("", [], name="translations", extra={"cs.txt": content})
        self.addCleanup(response.close)

        self.assertTrue(response.streaming)
        # A real file descriptor ensures the archive is stored on disk.
        assert response.file_to_stream is not None
        self.assertGreaterEqual(response.file_to_stream.fileno(), 0)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="translations.zip"'
        )
        archive_content = b"".join(response)
        self.assertEqual(int(response["Content-Length"]), len(archive_content))
        with ZipFile(BytesIO(archive_content)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("cs.txt"), content)

    def test_close_releases_temporary_file(self) -> None:
        for consume_chunk in (False, True):
            with self.subTest(consume_chunk=consume_chunk):
                response = zip_download("", [], extra={"cs.txt": b"translation" * 1000})
                self.addCleanup(response.close)
                snapshot = response.file_to_stream
                assert snapshot is not None
                if consume_chunk:
                    next(iter(response))
                self.assertFalse(snapshot.closed)

                response.close()

                self.assertTrue(snapshot.closed)

    def test_failure_releases_temporary_file(self) -> None:
        for target in (
            "FileResponse",
            "ZipFile",
            "write_zip_files",
            "ZipFile._write_end_record",
        ):
            with (
                self.subTest(target=target),
                tempfile.TemporaryFile() as snapshot,
                patch(
                    "weblate.utils.views.tempfile.TemporaryFile", return_value=snapshot
                ),
                patch(
                    f"weblate.utils.views.{target}",
                    side_effect=OSError("archive failed"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "archive failed"):
                    zip_download("", [])

                self.assertTrue(snapshot.closed)

    def test_archive_is_stable_after_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "cs.txt")
            source.write_bytes(b"original translation")
            response = zip_download(root, [str(source)])
            self.addCleanup(response.close)
            source.write_bytes(b"changed translation")

        with ZipFile(BytesIO(b"".join(response))) as archive:
            self.assertEqual(archive.read("cs.txt"), b"original translation")
