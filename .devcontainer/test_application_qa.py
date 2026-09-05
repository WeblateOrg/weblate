# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for bounded application QA polling and its self-contained fixture."""

from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import Mock, patch
from zipfile import ZipFile

from application_qa import fixture_archive, translated_in_page, verify_export, wait_for
from translate.storage.pypo import pofile


class ApplicationQATests(unittest.TestCase):
    def test_eventual_completion(self) -> None:
        probe = Mock(side_effect=[None, None, {"completed": True}])
        with patch("application_qa.time.sleep") as sleep:
            self.assertEqual(wait_for("import", probe), {"completed": True})
        self.assertEqual(sleep.call_count, 2)

    def test_deadline(self) -> None:
        with (
            patch("application_qa.time.monotonic", side_effect=[0, 1, 181]),
            patch("application_qa.time.sleep"),
            self.assertRaisesRegex(TimeoutError, "180s: notification"),
        ):
            wait_for("notification", lambda: False)

    def test_worker_failure_is_not_retried_by_polling(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "worker traceback"):
            wait_for("import", Mock(side_effect=RuntimeError("worker traceback")))

    def test_export_must_contain_committed_translation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "saved translation"):
            verify_export(fixture_archive(), "Ahoj")
        result = BytesIO()
        with ZipFile(result, "w") as archive:
            archive.writestr("messages/cs.po", 'msgstr "Ahoj"')
        verify_export(result.getvalue(), "Ahoj")

    def test_rendered_statistics(self) -> None:
        for count in (0, 1):
            content = f"<table><tr><th>Translated</th><td>100%</td><td>{count}</td></tr></table>".encode()
            self.assertEqual(translated_in_page(content), count == 1)
        self.assertFalse(translated_in_page(b"<h1>Still importing</h1>"))

    def test_fixture_is_parseable_untranslated_po(self) -> None:
        with ZipFile(BytesIO(fixture_archive())) as archive:
            store = pofile(BytesIO(archive.read("cs.po")))
        units = [unit for unit in store.units if not unit.isheader()]
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].source, "Hello Celery")
        self.assertFalse(units[0].istranslated())


if __name__ == "__main__":
    unittest.main()
