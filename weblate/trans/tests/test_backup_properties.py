# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import warnings
from io import BytesIO
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from hypothesis import example, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import SimpleTestCase

from weblate.trans.backups import ProjectBackup
from weblate.utils.zip import ZipSafetyError

SAFE_PATHS = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=24),
    min_size=1,
    max_size=4,
).map("/".join)


class BackupMemberPropertyTest(SimpleTestCase):
    def validate_members(self, names: list[str]) -> None:
        buffer = BytesIO()
        with warnings.catch_warnings():
            # Duplicate entries are deliberate inputs to the backup validator.
            warnings.filterwarnings(
                "ignore", message=r"Duplicate name: .*", category=UserWarning
            )
            with ZipFile(buffer, "w") as archive:
                for name in names:
                    archive.writestr(name, b"backup test")
        buffer.seek(0)
        backup = ProjectBackup(fileio=buffer)
        with ZipFile(buffer) as archive:
            backup.validate_zip_members(archive)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(st.lists(SAFE_PATHS, min_size=1, max_size=8, unique=True))
    @example(
        [
            "weblate-backup.json",
            "weblate-memory.json",
            "components/test.json",
            "vcs/test/.git/config",
        ]
    )
    def test_safe_members_are_accepted(self, names: list[str]) -> None:
        self.validate_members(names)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(
        name=SAFE_PATHS,
        template=st.sampled_from(
            [
                "../{}",
                "nested/../{}",
                "/{}",
                "C:/{}",
                "C:\\{}",
                "vcs/../{}",
                "vcs//{}",
                "vcs/C:/{}",
                "vcs/C:\\{}",
                "vcs/..\\{}",
            ]
        ),
    )
    @example(name="config", template="vcs/C:/{}")
    @example(name="config", template="vcs/../{}")
    def test_unsafe_members_are_rejected(self, name: str, template: str) -> None:
        with self.assertRaises((ZipSafetyError, ValidationError)):
            self.validate_members([template.format(name)])

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(SAFE_PATHS)
    @example("weblate-backup.json")
    def test_duplicate_members_are_rejected(self, name: str) -> None:
        with self.assertRaises(ZipSafetyError):
            self.validate_members([name, name])
