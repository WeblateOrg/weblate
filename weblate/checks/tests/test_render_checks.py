# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for rendering quality checks."""

from weblate.checks.render import MaxSizeCheck
from weblate.fonts.models import FontGroup, FontOverride
from weblate.fonts.tests.utils import FontTestCase
from weblate.utils.state import STATE_TRANSLATED


class MaxSizeCheckTest(FontTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.check = MaxSizeCheck()

    def perform_check(self, target: str, flags):
        unit = self.get_unit()
        unit.flags = flags
        unit.target = target
        unit.state = STATE_TRANSLATED
        return self.check.check_target(["source"], [target], unit)

    def test_good(self) -> None:
        self.assertFalse(self.perform_check("short", "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_bad_long(self) -> None:
        self.assertTrue(self.perform_check("long" * 50, "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_bad_multiline(self) -> None:
        self.assertTrue(self.perform_check("long " * 50, "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_good_multiline(self) -> None:
        self.assertFalse(self.perform_check("long " * 50, "max-size:500:50"))
        self.assertEqual(self.check.last_font, "sans")

    def add_font_group(self):
        font = self.add_font()
        return FontGroup.objects.create(name="droid", font=font, project=self.project)

    def test_custom_font(self) -> None:
        self.add_font_group()
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, "Kurinto Sans Regular")

    def test_custom_font_override(self) -> None:
        group = self.add_font_group()
        FontOverride.objects.create(
            group=group, language=self.get_translation().language, font=group.font
        )
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, "Kurinto Sans Regular")
