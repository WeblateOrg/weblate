# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management commands."""

import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class CommandsTest(SimpleTestCase):
    def test_list_format_features(self) -> None:

        with self.assertRaisesRegex(
            CommandError, "the following arguments are required: -o/--output"
        ):
            call_command("list_format_features")

        with (
            tempfile.NamedTemporaryFile(suffix=".rst", delete=False) as tmp_file,
            self.assertRaisesRegex(CommandError, "must be a directory"),
        ):
            call_command("list_format_features", "-o", tmp_file.name)

        with tempfile.TemporaryDirectory() as tmp_dir:
            call_command("list_format_features", "-o", tmp_dir)
            php_features_path = Path(tmp_dir) / "php-features.rst"
            self.assertTrue(php_features_path.exists())
            xliff2_features = (Path(tmp_dir) / "xliff2-features.rst").read_text(
                encoding="utf-8"
            )
            self.assertIn("``.xlf``, ``.xliff``", xliff2_features)

            snippets_dir = Path("docs/snippets/format-features")
            generated_files = sorted(Path(tmp_dir).glob("*-features.rst"))
            checked_in_files = sorted(snippets_dir.glob("*-features.rst"))

            self.assertEqual(
                [path.name for path in generated_files],
                [path.name for path in checked_in_files],
            )
            for generated_file, checked_in_file in zip(
                generated_files, checked_in_files, strict=True
            ):
                with self.subTest(snippet=generated_file.name):
                    self.assertEqual(
                        generated_file.read_text(encoding="utf-8"),
                        checked_in_file.read_text(encoding="utf-8"),
                    )
