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
