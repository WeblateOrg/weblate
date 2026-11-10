# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Host-side tests for verification readiness, selection, and enforcement."""

from __future__ import annotations

import argparse
import subprocess
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from environment import Environment, command_arguments
from mypy_check import enforced_diagnostics, run_mypy
from readiness import (
    INPUTS,
    check_image,
    check_preparation,
    check_tools,
    record_preparation,
)
from verify import commands, verify


class PreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))
        for name in (*INPUTS, "dev-docker/weblate-dev/Dockerfile"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        self.marker = self.root / "bootstrap.json"

    def test_missing_changed_and_corrupt_preparation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "bootstrap"):
            check_preparation(self.root, self.marker)
        record_preparation(self.root, self.marker)
        check_preparation(self.root, self.marker)
        for name in INPUTS:
            with self.subTest(name=name):
                path = self.root / name
                path.write_text("changed")
                with self.assertRaisesRegex(RuntimeError, "bootstrap"):
                    check_preparation(self.root, self.marker)
                record_preparation(self.root, self.marker)
        with (
            patch("readiness.platform.python_version", return_value="other"),
            self.assertRaisesRegex(RuntimeError, "bootstrap"),
        ):
            check_preparation(self.root, self.marker)
        self.marker.write_text("{")
        with self.assertRaisesRegex(RuntimeError, "bootstrap"):
            check_preparation(self.root, self.marker)

    def test_image_rebuild_and_missing_tools(self) -> None:
        image = self.root / "image"
        with patch("readiness.IMAGE_SOURCE", image):
            with self.assertRaisesRegex(RuntimeError, "rebuild|build"):
                check_image(self.root)
            image.write_bytes(
                (self.root / "dev-docker/weblate-dev/Dockerfile").read_bytes()
            )
            check_image(self.root)
            image.write_text("old")
            with self.assertRaisesRegex(RuntimeError, "build"):
                check_image(self.root)
        with (
            patch(
                "readiness.shutil.which",
                side_effect=lambda name: None if name == "dot" else name,
            ),
            self.assertRaisesRegex(RuntimeError, "dot"),
        ):
            check_tools()


class VerificationTests(unittest.TestCase):
    def test_launcher_uses_tests_without_bootstrapping(self) -> None:
        env = Environment(Path.cwd(), "app", "compose")
        with (
            patch.object(env, "execute", return_value=0) as execute,
            patch.object(env, "up") as up,
        ):
            self.assertEqual(env.verification("verify", ["--check", "docs"]), 0)
        self.assertEqual(env.profile, "tests")
        self.assertEqual(execute.call_args.args[0][-2:], ["--check", "docs"])
        up.assert_not_called()

    def test_invalid_selectors_and_versions_fail_before_execution(self) -> None:
        parser = argparse.ArgumentParser()
        for command, arguments in (
            ("verify", ["--check", "unknown"]),
            ("migration-test", []),
            ("migration-test", ["--help"]),
            ("migration-test", ["5.10", "5.14"]),
        ):
            with (
                self.subTest(command=command, arguments=arguments),
                redirect_stderr(StringIO()),
                self.assertRaises(SystemExit),
            ):
                command_arguments(parser, command, arguments)

    def test_independent_failures_and_duplicate_selection(self) -> None:
        with patch("verify.subprocess.call", side_effect=[0, 1, 0, 0]) as call:
            self.assertEqual(verify(Path.cwd(), ["lint", "types", "lint"]), 1)
        self.assertEqual(call.call_count, 4)
        self.assertIn("pylint", call.call_args_list[2].args[0])
        self.assertIn(".devcontainer/mypy_check.py", call.call_args_list[3].args[0])

    def test_stale_preparation_blocks_checks(self) -> None:
        with patch("verify.subprocess.call", return_value=1) as call:
            self.assertEqual(verify(Path.cwd(), ["frontend"]), 1)
        call.assert_called_once()

    def test_install_failure_does_not_build_stale_assets(self) -> None:
        with patch("verify.subprocess.call", side_effect=[0, 1, 0]) as call:
            self.assertEqual(verify(Path.cwd(), ["frontend", "types"]), 1)
        self.assertEqual(call.call_count, 3)
        self.assertNotIn("build", call.call_args_list[2].args[0])

    def test_frontend_build_destination(self) -> None:
        destination = Path("/temporary/build")
        install, build = commands("frontend", destination)
        self.assertIn("--frozen-lockfile", install)
        self.assertEqual(build[-1], str(destination / "static/js/vendor"))

    def test_mypy_enforcement_preserves_unexpected_errors(self) -> None:
        exclusions = "# comment\napi/(views|serializers)\n"
        output = "weblate/api/views.py:12:2: error: known\nweblate/api/new.py:1:2: error: new\nscripts/example.py:2:3: error: new\nFound 3 errors in 3 files (checked 4 source files)"
        self.assertEqual(
            enforced_diagnostics(output, exclusions), output.splitlines()[1:3]
        )

    def test_mypy_crash_is_not_masked_by_empty_filter(self) -> None:
        with patch(
            "mypy_check.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 2, stdout=""),
                subprocess.CompletedProcess([], 1, stdout=""),
            ],
        ):
            self.assertEqual(run_mypy(Path.cwd()), 1)

    def test_mypy_known_errors_are_reported_without_failure(self) -> None:
        output = "weblate/api/views.py:1:1: error: existing\nFound 1 error in 1 file (checked 2 source files)\n"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ci").mkdir()
            (root / "ci/mypy-exclusions.txt").write_text("api/views\n")
            with patch(
                "mypy_check.subprocess.run",
                side_effect=[
                    subprocess.CompletedProcess([], 1, stdout=output),
                    subprocess.CompletedProcess([], 0, stdout=output),
                ],
            ):
                self.assertEqual(run_mypy(root), 0)


if __name__ == "__main__":
    unittest.main()
