# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import tempfile
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from django.test import SimpleTestCase

from weblate.utils.zip import (
    ZipSafetyError,
    ZipSafetyLimits,
    iter_safe_zip_members,
    validate_zip_member_path,
    validate_zip_members,
)


class ZipSafetyTest(SimpleTestCase):
    def test_validate_zip_members_compressed_entry_thresholds(self) -> None:
        limits = ZipSafetyLimits(
            max_compressed_entry_size=100,
            min_compressed_ratio_size=10,
            max_compressed_entry_ratio=5,
        )
        for name, size, compression, rejected in (
            ("high ratio at size threshold", 100, ZIP_DEFLATED, False),
            ("high ratio above size threshold", 101, ZIP_DEFLATED, True),
            ("low ratio above size threshold", 101, ZIP_STORED, False),
        ):
            with self.subTest(name=name):
                archive = BytesIO()
                with ZipFile(archive, "w") as zipfile:
                    zipfile.writestr("entry", b"a" * size, compress_type=compression)
                archive.seek(0)

                with ZipFile(archive) as zipfile:
                    if rejected:
                        with self.assertRaisesRegex(
                            ZipSafetyError, "compressed entry that is too large"
                        ):
                            validate_zip_members(zipfile, limits=limits)
                    else:
                        validate_zip_members(zipfile, limits=limits)

    def test_validate_zip_members_minimum_ratio_size(self) -> None:
        limits = ZipSafetyLimits(
            max_compressed_entry_size=100,
            min_compressed_ratio_size=200,
            max_compressed_entry_ratio=5,
        )
        for size, rejected in ((199, False), (200, True)):
            with self.subTest(size=size):
                archive = BytesIO()
                with ZipFile(archive, "w") as zipfile:
                    zipfile.writestr("entry", b"a" * size, compress_type=ZIP_DEFLATED)
                archive.seek(0)

                with ZipFile(archive) as zipfile:
                    if rejected:
                        with self.assertRaisesRegex(
                            ZipSafetyError, "compressed entry that is too large"
                        ):
                            validate_zip_members(zipfile, limits=limits)
                    else:
                        validate_zip_members(zipfile, limits=limits)

    def test_validate_zip_members_rejects_dot_path(self) -> None:
        for filename in (".", "./"):
            with self.subTest(filename=filename):
                archive = BytesIO()
                with ZipFile(archive, "w") as zipfile:
                    zipfile.writestr(filename, "blocked")
                archive.seek(0)

                with (
                    ZipFile(archive) as zipfile,
                    self.assertRaisesRegex(ZipSafetyError, "contains invalid path"),
                ):
                    validate_zip_members(zipfile, limits=ZipSafetyLimits())

    def test_validate_zip_members_rejects_normalized_duplicates(self) -> None:
        archive = BytesIO()
        with ZipFile(archive, "w") as zipfile:
            zipfile.writestr("locale/cs.po", "first")
            zipfile.writestr(r"locale\cs.po", "second")
        archive.seek(0)

        with (
            ZipFile(archive) as zipfile,
            self.assertRaisesRegex(ZipSafetyError, "contains duplicate files"),
        ):
            validate_zip_members(zipfile, limits=ZipSafetyLimits())

    def test_validate_zip_members_uses_member_validator(self) -> None:
        archive = BytesIO()
        with ZipFile(archive, "w") as zipfile:
            zipfile.writestr("vcs/C:foo", "blocked")
        archive.seek(0)

        with (
            ZipFile(archive) as zipfile,
            self.assertRaisesRegex(ZipSafetyError, "contains invalid path"),
        ):
            validate_zip_members(
                zipfile,
                limits=ZipSafetyLimits(),
                validate_member=lambda info: validate_zip_member_path(
                    info.filename.removeprefix("vcs/")
                ),
            )

    def test_iter_safe_zip_members_honors_empty_members(self) -> None:
        archive = BytesIO()
        with ZipFile(archive, "w") as zipfile:
            zipfile.writestr("locale/cs.po", "content")
        archive.seek(0)

        with tempfile.TemporaryDirectory() as tempdir, ZipFile(archive) as zipfile:
            self.assertEqual(
                list(iter_safe_zip_members(zipfile, tempdir, members=[])), []
            )
