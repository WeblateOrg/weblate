# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import warnings
from unittest.mock import patch

from django.test import SimpleTestCase

from fuzzing.targets import (
    _assert_markdown_output_has_no_xss,
    fuzz_backups,
    fuzz_markup,
    fuzz_translation_formats,
)


class BackupFuzzTargetTest(SimpleTestCase):
    def test_duplicate_zip_members_are_ignored(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            fuzz_backups(
                bytes.fromhex(
                    "222043d16f2d332e302d6f722d7001000000636f64696e67732e7574665f3332696967"
                )
            )

    def test_invalid_member_paths_are_ignored(self) -> None:
        fuzz_backups(
            bytes.fromhex(
                "2320436f707972696768742020a92023726fc257730a0a77626c612320436f7079"
                "72696768742020a92023726fc257730a0a77626c616574652d6d656d6f7265626c"
                "61746520636f6e7472696275656e74736574652d6d656d6f7265626c6174652063"
                "6f6e7472696275656e7473d18b9c9a6e6669672f74636f6e66696765657373656c"
                "696e757866730a730a7474"
            )
        )

    def test_invalid_backup_timestamp_is_ignored(self) -> None:
        with patch(
            "weblate.trans.backups.ProjectBackup.load_data",
            side_effect=ValueError("Invalid isoformat string: 'broken'"),
        ):
            fuzz_backups(b"\x00")

    def test_unexpected_backup_value_error_is_not_ignored(self) -> None:
        with (
            patch(
                "weblate.trans.backups.ProjectBackup.load_data",
                side_effect=ValueError("unexpected failure"),
            ),
            self.assertRaisesRegex(ValueError, "unexpected failure"),
        ):
            fuzz_backups(b"\x00")


class TranslationFormatFuzzTargetTest(SimpleTestCase):
    def test_csv_parser_error_is_ignored(self) -> None:
        fuzz_translation_formats(
            b"input" + b"\0" * 19 + b"\x05" + b"\0" * 7 + b'"source","target"\r"a","b"'
        )

    def test_empty_csv_header_error_is_ignored(self) -> None:
        fuzz_translation_formats(
            b"input" + b"\0" * 19 + b"\x05" + b"\0" * 7 + b"\xff\xfe"
        )


class MarkupFuzzTargetTest(SimpleTestCase):
    def test_markdown_xss_payloads_are_safe(self) -> None:
        fuzz_markup(b'<img src=x onerror="alert(1)">')
        fuzz_markup(b"[link](javascript:alert(1))")
        fuzz_markup(b'![image](<https://example.com/" onerror="alert(1)>)')

    def test_markdown_xss_assertion_rejects_event_handlers(self) -> None:
        with self.assertRaisesRegex(AssertionError, "Unsafe markdown renderer output"):
            _assert_markdown_output_has_no_xss('<img src="x" onerror="alert(1)">')

    def test_markdown_xss_assertion_rejects_dangerous_urls(self) -> None:
        with self.assertRaisesRegex(AssertionError, "Unsafe markdown renderer output"):
            _assert_markdown_output_has_no_xss('<a href="javascript:alert(1)">link</a>')

    def test_markdown_fuzzer_rejects_unsafe_renderer_output(self) -> None:
        with (
            patch(
                "weblate.utils.markdown.render_markdown",
                return_value='<img src="x" onerror="alert(1)">',
            ),
            self.assertRaisesRegex(AssertionError, "Unsafe markdown renderer output"),
        ):
            fuzz_markup(b"input")
