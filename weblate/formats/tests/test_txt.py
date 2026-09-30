# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

from __future__ import annotations

import os.path
from pathlib import Path
from typing import IO
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError

from weblate.formats.tests.test_formats import BaseFormatTest
from weblate.formats.txt import AppStoreFormat, MultiparserError
from weblate.lang.models import Language
from weblate.trans.tests.utils import get_test_file

APPSTORE_FILE = get_test_file("short_description.txt")


class AppStoreFormatTest(BaseFormatTest):
    format_class = AppStoreFormat
    FILE = APPSTORE_FILE
    MIME = "text/plain"
    EXT = "txt"
    COUNT = 2
    MASK = "market/*"
    EXPECTED_PATH = "market/cs-CZ"
    FIND = "Hello world"
    FIND_CONTEXT = "short_description.txt:1"
    FIND_MATCH = "Hello world"
    MATCH = None
    BASE = os.path.dirname(APPSTORE_FILE)
    EXPECTED_FLAGS = "max-length:80"

    @staticmethod
    def validate_file(filename: str) -> str:
        return filename

    def parse_file(
        self, filename: str | IO[bytes], template: str | None = None
    ) -> AppStoreFormat:
        if not isinstance(filename, str):
            msg = "App store does not operate on files"
            raise TypeError(msg)
        if not os.path.isdir(filename):
            filename = os.path.dirname(filename)
        return self.format_class(filename, file_validator=self.validate_file)

    def test_add(self) -> None:
        self.assertTrue(
            self.format_class.is_valid_base_for_new(
                self.BASE,
                True,
                file_validator=self.validate_file,
                file_format_params=self.FILE_FORMAT_PARAMS,
            )
        )
        out = os.path.join(self.tempdir, f"test.{self.EXT}")
        self.format_class.add_language(
            out,
            Language.objects.get(code="cs"),
            self.BASE,
            file_format_params=self.FILE_FORMAT_PARAMS,
        )
        self.parse_file(out)
        self.assertTrue(os.path.isdir(out))

    def test_file_validator_required(self) -> None:
        with self.assertRaisesMessage(
            ValueError, "File validation is required for directory-based formats."
        ):
            self.format_class(self.BASE)

    def test_validates_file_before_parsing(self) -> None:
        base = Path(self.tempdir, "metadata")
        base.mkdir()
        linked_file = base / "title.txt"
        linked_file.symlink_to(Path(self.tempdir, "secret"))
        validator = Mock(
            side_effect=ValidationError("Invalid symbolic link in a repository.")
        )

        with (
            patch("weblate.formats.txt.TextParser") as parser,
            self.assertRaises(MultiparserError),
        ):
            self.format_class(str(base), file_validator=validator)

        validator.assert_called_once_with(str(linked_file))
        parser.assert_not_called()
