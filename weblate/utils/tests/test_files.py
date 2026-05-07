# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.test import SimpleTestCase

from weblate.utils.files import (
    REPO_TEMP_DIRNAME,
    get_repo_temp_dir,
    is_excluded,
    is_path_within_directory,
    read_file_bytes,
    remove_tree,
    should_skip,
)
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

    def test_is_excluded_rejects_path_traversal_and_absolute_paths(self) -> None:
        self.assertTrue(is_excluded("../outside.po"))
        self.assertTrue(is_excluded("/etc/passwd"))
        self.assertTrue(is_excluded(r"C:\temp\escape.po"))

    def test_is_excluded_allows_regular_relative_paths(self) -> None:
        self.assertFalse(is_excluded("locale/cs/messages.po"))

    def test_is_path_within_directory_accepts_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_path = os.path.join(tempdir, "repo")
            nested_path = os.path.join(repo_path, "locale", "cs.po")
            os.makedirs(os.path.dirname(nested_path))
            Path(nested_path).write_text("test", encoding="utf-8")

            self.assertTrue(is_path_within_directory(nested_path, repo_path))

    def test_is_path_within_directory_rejects_prefix_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_path = os.path.join(tempdir, "repo")
            outside_path = os.path.join(tempdir, "repo_outside", "secrets.po")
            os.makedirs(repo_path)
            os.makedirs(os.path.dirname(outside_path))
            Path(outside_path).write_text("test", encoding="utf-8")

            self.assertFalse(is_path_within_directory(outside_path, repo_path))

    def test_should_skip_rejects_prefix_collision(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tempdir,
            self.settings(
                DATA_DIR=os.path.join(tempdir, "data"),
            ),
        ):
            location = os.path.join(tempdir, "weblate-other", "locale", "django.po")
            os.makedirs(os.path.dirname(location))
            Path(location).write_text("test", encoding="utf-8")

            self.assertTrue(should_skip(location))

    def test_get_repo_temp_dir_prefers_explicit_temp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            locale = repo / "locale"
            locale.mkdir(parents=True)
            (repo / ".git").mkdir()
            filename = locale / "cs.po"
            temp_dir = repo / ".git" / REPO_TEMP_DIRNAME

            self.assertEqual(
                get_repo_temp_dir(filename, temp_dir=temp_dir),
                temp_dir,
            )

    def test_get_repo_temp_dir_does_not_create_unused_target_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            filename = repo / "locale" / "cs.po"
            temp_dir = repo / ".git" / REPO_TEMP_DIRNAME

            self.assertEqual(
                get_repo_temp_dir(filename, temp_dir=temp_dir),
                temp_dir,
            )
            self.assertTrue(temp_dir.is_dir())
            self.assertFalse(filename.parent.exists())

    def test_get_repo_temp_dir_avoids_cross_device_explicit_temp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            locale = repo / "locale"
            locale.mkdir(parents=True)
            (repo / ".git").mkdir()
            filename = locale / "docs.pot"
            temp_dir = repo / ".git" / REPO_TEMP_DIRNAME
            resolved_locale = locale.resolve(strict=False)
            resolved_temp_dir = temp_dir.resolve(strict=False)

            def fake_get_path_device_id(path: Path) -> int | None:
                resolved = path.resolve(strict=False)
                if resolved == resolved_locale:
                    return 1
                if resolved == resolved_temp_dir:
                    return 2
                return None

            with patch(
                "weblate.utils.files._get_path_device_id",
                side_effect=fake_get_path_device_id,
            ):
                self.assertEqual(
                    get_repo_temp_dir(filename, temp_dir=temp_dir).resolve(
                        strict=False
                    ),
                    resolved_locale,
                )

    def test_get_repo_temp_dir_avoids_unknown_explicit_device(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            locale = repo / "locale"
            locale.mkdir(parents=True)
            (repo / ".git").mkdir()
            filename = locale / "docs.pot"
            temp_dir = repo / ".git" / REPO_TEMP_DIRNAME
            resolved_locale = locale.resolve(strict=False)
            resolved_temp_dir = temp_dir.resolve(strict=False)

            def fake_get_path_device_id(path: Path) -> int | None:
                resolved = path.resolve(strict=False)
                if resolved == resolved_locale:
                    return 1
                if resolved == resolved_temp_dir:
                    return None
                return 1

            with patch(
                "weblate.utils.files._get_path_device_id",
                side_effect=fake_get_path_device_id,
            ):
                self.assertEqual(
                    get_repo_temp_dir(filename, temp_dir=temp_dir).resolve(
                        strict=False
                    ),
                    resolved_locale,
                )
