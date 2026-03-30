# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from weblate.trans.tests.utils import TempDirMixin
from weblate.utils.commands import find_runtime_command, get_clean_env


class CommandTests(SimpleTestCase, TempDirMixin):
    def test_queues(self) -> None:
        output = StringIO()
        call_command("celery_queues", stdout=output)
        self.assertIn("celery:", output.getvalue())


class DBCommandTests(TestCase):
    def test_stats(self) -> None:
        output = StringIO()
        call_command("ensure_stats", stdout=output)
        self.assertEqual("found 0 strings\n", output.getvalue())


class RuntimeCommandTests(SimpleTestCase):
    def test_get_clean_env_includes_runtime_and_venv_paths(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "/runtime/bin/python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
        ):
            env = get_clean_env(extra_path="/extra/bin")

        self.assertEqual(
            env["PATH"],
            "/extra/bin:/runtime/bin:/venv-prefix/bin:/usr/bin",
        )

    def test_get_clean_env_skips_relative_runtime_path(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
        ):
            env = get_clean_env(extra_path="/extra/bin")

        self.assertEqual(
            env["PATH"],
            "/extra/bin:/venv-prefix/bin:/usr/bin",
        )

    def test_get_clean_env_skips_empty_runtime_path(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", ""),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
        ):
            env = get_clean_env(extra_path="/extra/bin")

        self.assertEqual(
            env["PATH"],
            "/extra/bin:/venv-prefix/bin:/usr/bin",
        )

    def test_find_runtime_command_uses_runtime_path(self) -> None:
        with (
            patch(
                "weblate.utils.commands.find_command",
                side_effect=lambda command, path=None: shutil.which(
                    command,
                    path=None if path is None else os.pathsep.join(path),
                ),
            ),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
            tempfile.TemporaryDirectory(prefix="weblate-runtime-command-") as tempdir,
        ):
            runtime_bin = Path(tempdir) / "runtime-bin"
            runtime_bin.mkdir(parents=True, exist_ok=True)
            fake_python = runtime_bin / "python"
            fake_python.write_text("", encoding="utf-8")
            fake_python.chmod(0o755)
            xgettext = runtime_bin / "xgettext"
            xgettext.write_text("", encoding="utf-8")
            xgettext.chmod(0o755)

            with patch("weblate.utils.commands.sys.executable", os.fspath(fake_python)):
                self.assertEqual(
                    find_runtime_command("xgettext"),
                    os.fspath(xgettext),
                )

    def test_find_runtime_command_ignores_relative_runtime_path(self) -> None:
        with (
            patch("weblate.utils.commands.find_command", return_value=None),
            patch("weblate.utils.commands.sys.executable", "python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
        ):
            self.assertIsNone(find_runtime_command("xgettext"))

    def test_find_runtime_command_passes_split_path_entries(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "/runtime/bin/python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {"PATH": "/usr/bin:/usr/local/bin"}),
            patch("weblate.utils.commands.find_command", return_value=None) as mocked,
        ):
            find_runtime_command("xgettext", extra_path="/extra/bin")

        self.assertEqual(
            mocked.call_args.kwargs["path"],
            [
                "/extra/bin",
                "/runtime/bin",
                "/venv-prefix/bin",
                "/usr/bin",
                "/usr/local/bin",
            ],
        )

    def test_get_clean_env_preserves_existing_path_precedence(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "/runtime/bin/python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(
                os.environ,
                {
                    "PATH": "/custom/bin:/extra/bin:/runtime/bin:/venv-prefix/bin:/usr/bin"
                },
            ),
        ):
            env = get_clean_env(extra_path="/extra/bin")

        self.assertEqual(
            env["PATH"],
            "/custom/bin:/extra/bin:/runtime/bin:/venv-prefix/bin:/usr/bin",
        )

    def test_find_runtime_command_uses_default_path_when_unset(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "/runtime/bin/python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv-prefix"),
            patch.dict(os.environ, {}, clear=True),
            patch("weblate.utils.commands.find_command", return_value=None) as mocked,
        ):
            find_runtime_command("xgettext", extra_path="/extra/bin")

        self.assertEqual(
            mocked.call_args.kwargs["path"],
            [
                "/extra/bin",
                "/runtime/bin",
                "/venv-prefix/bin",
                "/bin",
                "/usr/bin",
                "/usr/local/bin",
            ],
        )

    def test_get_clean_env_deduplicates_runtime_prefixes(self) -> None:
        with (
            patch("weblate.utils.commands.sys.executable", "/venv/bin/python"),
            patch("weblate.utils.commands.sys.exec_prefix", "/venv"),
            patch.dict(os.environ, {"PATH": "/usr/bin"}),
        ):
            env = get_clean_env()

        self.assertEqual(env["PATH"], "/venv/bin:/usr/bin")
