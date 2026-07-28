# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for rendering quality checks."""

from unittest.mock import patch

from weblate.checks.render import MaxSizeCheck
from weblate.fonts.models import FONT_STORAGE, Font, FontGroup, FontOverride
from weblate.fonts.tests.utils import FONT_BOLD, FontTestCase
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

    def perform_source_check(self, source: str, flags):
        unit = self.get_unit().source_unit
        unit.extra_flags = flags
        unit.source = source
        return self.check.check_source(unit.get_source_plurals(), unit)

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

    def test_source_good(self) -> None:
        self.assertFalse(self.perform_source_check("short", "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_source_bad_long(self) -> None:
        self.assertTrue(self.perform_source_check("long" * 50, "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_source_bad_invalid_flag(self) -> None:
        self.assertTrue(self.perform_source_check("short", "max-size:invalid"))

    def add_font_group(self):
        font = self.add_font()
        return FontGroup.objects.create(name="droid", font=font, project=self.project)

    def test_custom_font(self) -> None:
        group = self.add_font_group()
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, group.font.font.path)

    @patch("weblate.checks.render.check_render_size", return_value=True)
    def test_custom_font_uses_same_family_faces(self, check_render_size_mock) -> None:
        self.add_font_group()
        with FONT_BOLD.open("rb") as handle:
            fontfile = FONT_STORAGE.save(FONT_BOLD.name, handle)
        bold_font = Font.objects.create(
            font=fontfile,
            project=self.project,
            user=self.user,
        )

        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))

        self.assertEqual(
            check_render_size_mock.call_args.kwargs["font_siblings"],
            (bold_font.font.path,),
        )

    def test_custom_font_override(self) -> None:
        group = self.add_font_group()
        FontOverride.objects.create(
            group=group, language=self.get_translation().language, font=group.font
        )
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, group.font.font.path)
