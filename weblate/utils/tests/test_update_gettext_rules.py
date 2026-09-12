# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from lxml.etree import XMLSyntaxError


class UpdateGettextRulesTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repository = Path(__file__).resolve().parents[3]
        script = self.repository / "scripts" / "update-gettext-rules.py"
        spec = importlib.util.spec_from_file_location("update_gettext_rules", script)
        if spec is None or spec.loader is None:
            msg = "Could not load update-gettext-rules.py"
            raise RuntimeError(msg)
        self.updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.updater)
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.readme = self.root / "README.md"
        self.readme.write_text(
            f"Manual introduction\n{self.updater.START_MARKER}\nold table\n"
            f"{self.updater.END_MARKER}\nManual instructions\n",
            encoding="utf-8",
        )
        self.source = self.updater.RuleSource(
            "example", "1.2.3", "https://github.com/example/project", "rules"
        )
        self.enterContext(patch.object(self.updater, "SOURCES", (self.source,)))
        self.rules = {
            "its": b'<its:rules xmlns:its="http://www.w3.org/2005/11/its" version="2.0"/>',
            "loc": b'<locatingRules><locatingRule pattern="*.xml" target="example.its"/></locatingRules>',
        }
        self.fetch = self.enterContext(
            patch.object(
                self.updater,
                "fetch_rule",
                side_effect=lambda url: self.rules[url.rsplit(".", 1)[1]],
            )
        )

    def test_update_and_idempotency(self) -> None:
        self.assertTrue(self.updater.update_rules(self.root))
        self.assertEqual(
            (self.root / "its/example.its").read_bytes(), self.rules["its"]
        )
        content = self.readme.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("Manual introduction\n"))
        self.assertTrue(content.endswith("\nManual instructions\n"))
        self.assertIn("| example.* | 1.2.3 |", content)
        self.assertIn("https://github.com/example/project/tree/1.2.3/rules", content)
        with patch.object(Path, "write_bytes") as write:
            self.assertFalse(self.updater.update_rules(self.root))
        write.assert_not_called()

    def test_check_does_not_write(self) -> None:
        before = self.readme.read_bytes()
        self.assertTrue(self.updater.update_rules(self.root, check=True))
        self.assertEqual(self.readme.read_bytes(), before)
        self.assertFalse((self.root / "its").exists())

    def test_obsolete_rules(self) -> None:
        self.updater.update_rules(self.root)
        rules = self.root / "its"
        obsolete = [rules / "old.its", rules / "old.loc"]
        for path in obsolete:
            path.write_bytes(b"old rule")
        unrelated = rules / "README.md"
        unrelated.write_bytes(b"Keep this file")
        nested = rules / "nested.its"
        nested.mkdir()
        (nested / "keep.its").write_bytes(b"Keep nested files")

        with patch("builtins.print") as output:
            self.assertTrue(self.updater.update_rules(self.root, check=True))
        for path in obsolete:
            output.assert_any_call(f"Obsolete its/{path.name}")
            self.assertEqual(path.read_bytes(), b"old rule")

        self.assertTrue(self.updater.update_rules(self.root))
        for path in obsolete:
            self.assertFalse(path.exists())
        self.assertEqual(unrelated.read_bytes(), b"Keep this file")
        self.assertEqual((nested / "keep.its").read_bytes(), b"Keep nested files")
        self.assertFalse(self.updater.update_rules(self.root, check=True))

    def test_failed_update_preserves_existing_rules(self) -> None:
        self.updater.update_rules(self.root)
        obsolete = self.root / "its/old.loc"
        obsolete.write_bytes(b"old rule")
        before = {
            path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        for error in (OSError("Download failed"), ValueError("Invalid XML")):
            with (
                self.subTest(error=error),
                patch.object(
                    self.updater,
                    "fetch_rule" if isinstance(error, OSError) else "validate_pair",
                    side_effect=error,
                ),
                self.assertRaises(type(error)),
            ):
                self.updater.update_rules(self.root)
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_download_failure_does_not_write(self) -> None:
        before = self.readme.read_bytes()
        self.fetch.side_effect = [self.rules["its"], OSError("Download failed")]
        with self.assertRaisesMessage(OSError, "Download failed"):
            self.updater.update_rules(self.root)
        self.assertEqual(self.readme.read_bytes(), before)
        self.assertFalse((self.root / "its").exists())

    def test_invalid_xml_does_not_write(self) -> None:
        before = self.readme.read_bytes()
        for data in (
            b"<html>Download failed</html>",
            b"<locatingRules>",
            b'<locatingRules><locatingRule pattern="*" target="../outside.its"/></locatingRules>',
            b'<!DOCTYPE locatingRules [<!ENTITY x "secret">]><locatingRules/>',
        ):
            with self.subTest(data=data):
                self.rules["loc"] = data
                with self.assertRaises((ValueError, XMLSyntaxError)):
                    self.updater.update_rules(self.root)
                self.assertEqual(self.readme.read_bytes(), before)
                self.assertFalse((self.root / "its").exists())

    def test_renovate_discovers_all_pins(self) -> None:
        configuration = json.loads(
            (self.repository / ".github/renovate.json").read_text(encoding="utf-8")
        )
        manager = next(
            manager
            for manager in configuration["customManagers"]
            if manager["description"] == "Update pinned upstream ITS rule releases"
        )
        expression = manager["matchStrings"][0].replace("(?<", "(?P<")
        script = (self.repository / "scripts/update-gettext-rules.py").read_text(
            encoding="utf-8"
        )
        dependencies = {
            match["depName"]: match for match in re.finditer(expression, script)
        }
        self.assertEqual(
            set(dependencies),
            {
                "polkit-org/polkit",
                "ximion/appstream",
                "GNOME/glib",
                "GNOME/gtk",
                "xdg/shared-mime-info",
            },
        )
        self.assertEqual(
            dependencies["xdg/shared-mime-info"]["registryUrl"],
            "https://gitlab.freedesktop.org",
        )
        self.assertEqual(
            dependencies["polkit-org/polkit"]["currentValue"],
            self.updater.POLKIT_VERSION,
        )
