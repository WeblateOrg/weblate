# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
from unittest import TestCase
from unittest.mock import patch

from fuzzing import sentry


class FuzzingSentryTest(TestCase):
    def setUp(self) -> None:
        # ruff: ignore[private-member-access]
        sentry._STATE["initialized"] = False

    def tearDown(self) -> None:
        # ruff: ignore[private-member-access]
        sentry._STATE["initialized"] = False

    def test_wrap_target_reports_exception(self) -> None:
        def callback(_data: bytes) -> None:
            msg = "boom"
            raise ValueError(msg)

        environ = {
            "SENTRY_DSN": "https://public@example.invalid/1",
            "CFLITE_MODE": "batch",
            "SANITIZER": "address",
            "GITHUB_REPOSITORY": "WeblateOrg/weblate",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "abc123",
            "GITHUB_WORKFLOW": "ClusterFuzzLite Batch Fuzzing",
        }

        with (
            patch.object(sentry.os, "environ", environ),
            patch("fuzzing.sentry.sentry_sdk.init") as init_mock,
            patch("fuzzing.sentry.sentry_sdk.capture_exception") as capture_mock,
            patch("fuzzing.sentry.sentry_sdk.flush") as flush_mock,
            self.assertRaisesRegex(ValueError, "boom"),
        ):
            sentry.wrap_target("backups", callback)(b"payload")

        init_mock.assert_called_once()
        capture_mock.assert_called_once()
        flush_mock.assert_called_once_with(timeout=10)
        _, kwargs = capture_mock.call_args
        self.assertEqual(
            kwargs["fingerprint"][:4],
            ["clusterfuzzlite", "address", "backups", "builtins.ValueError"],
        )
        self.assertEqual(kwargs["tags"]["target"], "backups")
        self.assertEqual(kwargs["contexts"]["fuzz_input"]["size"], 7)
        self.assertEqual(
            kwargs["contexts"]["fuzz_input"]["sha256"],
            hashlib.sha256(b"payload").hexdigest(),
        )
        self.assertEqual(
            kwargs["contexts"]["fuzz_input"]["attachment_filename"],
            "fuzz-input-backups.bin",
        )
        self.assertEqual(kwargs["contexts"]["fuzz_input"]["attachment_size"], 7)
        self.assertFalse(kwargs["contexts"]["fuzz_input"]["attachment_truncated"])
        self.assertEqual(
            kwargs["contexts"]["github_actions"]["run_url"],
            "https://github.com/WeblateOrg/weblate/actions/runs/123",
        )

    def test_wrap_target_skips_sentry_without_dsn(self) -> None:
        def callback(_data: bytes) -> None:
            msg = "boom"
            raise ValueError(msg)

        with (
            patch.object(sentry.os, "environ", {}),
            patch("fuzzing.sentry.sentry_sdk.capture_exception") as capture_mock,
            self.assertRaisesRegex(ValueError, "boom"),
        ):
            sentry.wrap_target("backups", callback)(b"payload")

        capture_mock.assert_not_called()

    def test_wrap_target_does_not_mask_fuzz_exception_on_sentry_failure(self) -> None:
        def callback(_data: bytes) -> None:
            msg = "original crash"
            raise ValueError(msg)

        with (
            patch(
                "fuzzing.sentry.capture_fuzz_exception",
                side_effect=RuntimeError("sentry failed"),
            ),
            self.assertLogs("fuzzing.sentry", level="WARNING") as logs,
            self.assertRaisesRegex(ValueError, "original crash"),
        ):
            sentry.wrap_target("backups", callback)(b"payload")

        self.assertIn("Could not report fuzz exception to Sentry", logs.output[0])

    def test_fuzz_input_attachment_is_limited_and_named(self) -> None:
        class Scope:
            def __init__(self) -> None:
                self.attachments: list[dict[str, object]] = []

            def add_attachment(self, **kwargs: object) -> None:
                self.attachments.append(kwargs)

        scope = Scope()
        with patch("fuzzing.sentry.MAX_INPUT_ATTACHMENT_BYTES", 4):
            # ruff: ignore[private-member-access]
            sentry._attach_fuzz_input(scope, "backup/import", b"payload")
            # ruff: ignore[private-member-access]
            context = sentry._input_context("backup/import", b"payload")

        self.assertEqual(
            scope.attachments,
            [
                {
                    "bytes": b"payl",
                    "filename": "fuzz-input-backup-import.bin",
                    "content_type": "application/octet-stream",
                }
            ],
        )
        self.assertEqual(context["attachment_filename"], "fuzz-input-backup-import.bin")
        self.assertEqual(context["attachment_size"], 4)
        self.assertTrue(context["attachment_truncated"])
        self.assertEqual(
            context["attachment_sha256"], hashlib.sha256(b"payl").hexdigest()
        )
