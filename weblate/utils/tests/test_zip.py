# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import tempfile
from io import BytesIO
from zipfile import ZipFile

from django.test import SimpleTestCase

from weblate.utils.zip import (
    ZipSafetyError,
    ZipSafetyLimits,
    iter_safe_zip_members,
    validate_zip_member_path,
    validate_zip_members,
)


class ZipSafetyTest(SimpleTestCase):
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
