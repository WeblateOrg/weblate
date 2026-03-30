# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for fonts."""

from __future__ import annotations

from django.core.cache import cache
from django.core.files.base import File
from django.test import SimpleTestCase

from weblate.fonts.tests.utils import FONT, FONT_NAME, FontTestCase
from weblate.fonts.utils import check_render_size, get_font_name, get_font_weight


class RenderTest(SimpleTestCase):
    def test_render(self) -> None:
        self.assertTrue(
            check_render_size(
                font="sans",
                weight=get_font_weight("normal"),
                size=12,
                spacing=0,
                text="ahoj",
                width=100,
                lines=1,
            )
        )
        self.assertFalse(
            check_render_size(
                font="sans",
                weight=get_font_weight("normal"),
                size=12,
                spacing=0,
                text="ahoj",
                width=10,
                lines=1,
            )
        )

    def test_render_cache(self) -> None:
        cache_key = "test:render:cache"

        def invoke() -> bool:
            return check_render_size(
                font="sans",
                weight=get_font_weight("normal"),
                size=12,
                spacing=0,
                text="ahoj",
                width=100,
                lines=1,
                cache_key=cache_key,
            )

        self.assertTrue(invoke())
        cache.delete(cache_key)
        self.assertFalse(cache.has_key(cache_key))

        self.assertTrue(invoke())
        self.assertTrue(cache.has_key(cache_key))


class FontNameTest(FontTestCase):
    def test_get_font_name_repeated_for_uploaded_file(self) -> None:
        with FONT.open("rb") as handle:
            uploaded = File(handle, name=FONT_NAME)

            self.assertEqual(get_font_name(uploaded), ("Kurinto Sans", "Regular"))
            self.assertEqual(get_font_name(uploaded), ("Kurinto Sans", "Regular"))
            self.assertEqual(uploaded.tell(), 0)
            self.assertTrue(uploaded.read(4))

    def test_get_font_name_repeated_for_field_file(self) -> None:
        font = self.add_font()

        self.assertEqual(get_font_name(font.font), ("Kurinto Sans", "Regular"))
        self.assertEqual(get_font_name(font.font), ("Kurinto Sans", "Regular"))

        with font.font.open("rb"):
            self.assertTrue(font.font.read(4))
