# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import warnings
from unittest.mock import patch

from django.test import SimpleTestCase

from fuzzing.targets import fuzz_backups


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
