# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check-rst-headings.py"


class RstHeadingsTest(TestCase):
    def run_check(
        self,
        *contents: str,
        github_actions: str = "",
        filename_prefix: str = "document",
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, content in enumerate(contents):
                path = Path(directory) / f"{filename_prefix}-{index}.rst"
                path.write_text(content, encoding="utf-8")
                paths.append(str(path))
            return subprocess.run(
                [sys.executable, str(SCRIPT), *paths],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "GITHUB_ACTIONS": github_actions},
            )

    def test_github_actions_annotations(self) -> None:
        result = self.run_check(
            "======\nHeading\n========\n", "Next\n---\n", github_actions="true"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        annotations = result.stdout.splitlines()
        self.assertEqual(len(annotations), 3)
        for annotation, location, length, expected in zip(
            annotations,
            ("document-0.rst,line=1", "document-0.rst,line=3", "document-1.rst,line=2"),
            (6, 8, 3),
            (7, 7, 4),
            strict=True,
        ):
            self.assertTrue(annotation.startswith("::error file="), annotation)
            self.assertTrue(
                annotation.endswith(
                    f"{location}::heading adornment has {length} "
                    f"characters; expected {expected}"
                ),
                annotation,
            )

    def test_github_actions_filename_escaping(self) -> None:
        result = self.run_check(
            "Heading\n===\n",
            github_actions="true",
            filename_prefix="name%25,:\r\n::error::",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertIn(
            "name%2525%2C%3A%0D%0A%3A%3Aerror%3A%3A-0.rst,line=2::",
            result.stdout,
        )

    def test_annotations_disabled_outside_github_actions(self) -> None:
        for value in ("", "false"):
            with self.subTest(value=value):
                result = self.run_check("Heading\n===\n", github_actions=value)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("::error", result.stdout)
                self.assertIn("document-0.rst:2: heading adornment", result.stdout)

    def test_matching_heading_has_no_annotation(self) -> None:
        result = self.run_check("Heading\n=======\n", github_actions="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_matching_adornments(self) -> None:
        for character in "=-+~^*`#":
            for title in ("Heading", "Příručka", "Using ``code``", "A"):
                for overline in ("", f"{character * len(title)}\n"):
                    with self.subTest(
                        character=character, title=title, overline=overline
                    ):
                        result = self.run_check(
                            f"{overline}{title}\n{character * len(title)}\n"
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, "")

    def test_mismatched_underlines(self) -> None:
        for character in "=-+~^*`#":
            for length in (1, 6, 8):
                with self.subTest(character=character, length=length):
                    result = self.run_check(f"Heading\n{character * length}\n")
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(
                        f"document-0.rst:2: heading adornment has {length} "
                        "characters; expected 7\n",
                        result.stdout,
                    )

    def test_mismatched_overline(self) -> None:
        result = self.run_check("======\nHeading\n=======\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "document-0.rst:1: heading adornment has 6 characters; expected 7\n",
            result.stdout,
        )

    def test_all_mismatches_are_reported(self) -> None:
        result = self.run_check(
            "======\nHeading\n========\n\nNext\n---\n",
            "Valid\n=====\n",
            "Last\n=====\n",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 4)
        for location in (
            "document-0.rst:1:",
            "document-0.rst:3:",
            "document-0.rst:6:",
            "document-2.rst:2:",
        ):
            self.assertIn(location, result.stdout)

    def test_non_headings_are_ignored(self) -> None:
        for content in (
            "",
            "Plain text\n",
            "Paragraph\n\n----\n",
            ".. code-block:: rst\n\n   Example\n   ===\n",
            "+-------+\n| Table |\n+=======+\n| Cell  |\n+-------+\n",
            "=======\n=======\n",
            "Paragraph\ncontinues here\n----\n",
        ):
            with self.subTest(content=content):
                result = self.run_check(content)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_no_final_newline(self) -> None:
        result = self.run_check("Heading\n===")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("document-0.rst:2:", result.stdout)

    def test_source_length_includes_unicode_and_markup(self) -> None:
        for title in ("Příručka", "Using ``code``"):
            with self.subTest(title=title):
                result = self.run_check(f"{title}\n{'=' * (len(title) - 1)}\n")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"expected {len(title)}\n", result.stdout)
