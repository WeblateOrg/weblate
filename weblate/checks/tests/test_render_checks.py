# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for rendering quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock, patch

from django.db.models.fields.files import FieldFile

from weblate.checks.render import MaxSizeCheck
from weblate.fonts.models import FontGroup, FontOverride
from weblate.fonts.tests.utils import FONT_BOLD, FontTestCase
from weblate.utils.data import data_dir
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from unittest.mock import Mock


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

    def test_oversized_flags_and_expansion_do_not_render(self) -> None:
        for text, flags in (
            ("short", "max-size:24000:1000"),
            ("short", "max-size:100, font-size:999999"),
            ("a" * 10000, "max-size:100, replacements:a:aaa"),
        ):
            with (
                self.subTest(flags=flags),
                patch("weblate.checks.render.check_render_size") as renderer,
            ):
                self.assertTrue(self.perform_check(text, flags))
                renderer.assert_not_called()

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
        self.assertEqual(self.check.last_font, group.font.get_local_path())

    @patch("weblate.checks.render.check_render_size", return_value=True)
    def test_custom_font_uses_same_family_faces(
        self, check_render_size_mock: Mock
    ) -> None:
        self.add_font_group()
        bold_font = self.add_font(FONT_BOLD)

        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))

        self.assertEqual(
            check_render_size_mock.call_args.kwargs["font_siblings"],
            (bold_font.get_local_path(),),
        )

    def test_custom_font_without_path(self) -> None:
        group = self.add_font_group()
        bold_font = self.add_font(FONT_BOLD)
        # Remote storage backends do not provide local paths
        with patch.object(
            FieldFile,
            "path",
            new_callable=PropertyMock,
            side_effect=NotImplementedError,
        ):
            self.assertFalse(
                self.perform_check("short", "max-size:500,font-family:droid")
            )
            self.assertTrue(
                self.perform_check("long" * 50, "max-size:500,font-family:droid")
            )
            last_font = self.check.last_font
            assert last_font is not None
            # Rendering uses a local copy of the stored font
            self.assertNotEqual(Path(last_font).parent, Path(data_dir("fonts")))
            with group.font.font.open("rb") as handle:
                self.assertEqual(Path(last_font).read_bytes(), handle.read())
            self.assertEqual(
                self.check.load_font(
                    self.project, self.get_translation().language, "droid"
                ),
                (last_font, (bold_font.get_local_path(),)),
            )

    def test_custom_font_missing_file(self) -> None:
        group = self.add_font_group()
        group.font.font.delete(save=False)
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, "sans")

    def test_custom_font_missing_sibling(self) -> None:
        group = self.add_font_group()
        bold_font = self.add_font(FONT_BOLD)
        bold_font.font.delete(save=False)
        # The selected font is still used, only the missing face is skipped
        self.assertEqual(
            self.check.load_font(
                self.project, self.get_translation().language, "droid"
            ),
            (group.font.get_local_path(), ()),
        )

    def test_custom_font_override(self) -> None:
        group = self.add_font_group()
        FontOverride.objects.create(
            group=group, language=self.get_translation().language, font=group.font
        )
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, group.font.get_local_path())
