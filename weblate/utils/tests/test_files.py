# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from io import BytesIO
from pathlib import Path
from typing import cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.test import SimpleTestCase

from weblate.utils.files import read_file_bytes, remove_tree
from weblate.utils.unittest import tempdir_setting


class FilesTestCase(SimpleTestCase):
    @tempdir_setting("DATA_DIR")
    def test_remove(self, callback=None) -> None:
        target = os.path.join(settings.DATA_DIR, "test")
        nested = os.path.join(target, "nested")
        filename = os.path.join(target, "file")
        os.makedirs(target)
        os.makedirs(nested)
        Path(filename).write_text("test", encoding="utf-8")
        if callback:
            callback(target, nested, filename)
        remove_tree(target)
        self.assertFalse(os.path.exists(target))

    def test_remove_readonly(self) -> None:
        def callback_readonly(target, nested, filename) -> None:
            os.chmod(target, 0)

        self.test_remove(callback_readonly)

    def test_remove_nested(self) -> None:
        def callback_readonly(target, nested, filename) -> None:
            os.chmod(nested, 0)

        self.test_remove(callback_readonly)

    def test_read_file_bytes_rejects_oversized_file(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Uploaded file is too big."):
            read_file_bytes(File(BytesIO(b"test"), name="test.bin"), max_size=3)

    def test_read_file_bytes_rejects_oversized_file_without_size(self) -> None:
        class FileWithoutSize(BytesIO):
            @property
            def size(self):
                raise AttributeError

        with self.assertRaisesMessage(ValidationError, "Uploaded file is too big."):
            read_file_bytes(cast("File", FileWithoutSize(b"test")), max_size=3)

    def test_read_file_bytes_resets_position_to_start(self) -> None:
        filelike = File(BytesIO(b"test"), name="test.bin")
        filelike.seek(2)

        self.assertEqual(read_file_bytes(filelike, max_size=10), b"test")
        self.assertEqual(filelike.tell(), 0)
