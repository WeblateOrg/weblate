# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for fonts."""

from __future__ import annotations

from io import BytesIO

from django.core.cache import cache
from django.core.files.base import File
from django.test import SimpleTestCase
from PIL import Image

from weblate.fonts.tests.utils import FONT, FONT_NAME, FontComponentTestCase
from weblate.fonts.utils import (
    _render_size,
    check_render_size,
    get_font_name,
    get_font_weight,
)


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

    def test_render_overflow_is_visible_in_red(self) -> None:
        _, _, buffer = _render_size(
            text="This text fills 70% long_word",
            font="sans",
            weight=get_font_weight("normal"),
            size=19,
            spacing=0,
            width=180,
            lines=1,
            needs_output=True,
        )

        image = Image.open(BytesIO(buffer)).convert("RGB")
        cropped = image.crop((0, image.height // 2, image.width, image.height))
        pixels = cropped.load()

        self.assertEqual(image.size[0], 180)
        self.assertGreaterEqual(image.size[1], 40)
        self.assertTrue(
            any(
                pixels[x, y][0] > 200
                and pixels[x, y][1] < 160
                and pixels[x, y][2] < 160
                for x in range(cropped.width)
                for y in range(cropped.height)
            )
        )

    def test_render_output_rescales_from_small_surface(self) -> None:
        pixel_size, _, buffer = _render_size(
            text="This text fills 70% long_word",
            font="sans",
            weight=get_font_weight("normal"),
            size=19,
            spacing=0,
            width=180,
            lines=1,
            needs_output=True,
            surface_width=50,
            surface_height=10,
        )

        image = Image.open(BytesIO(buffer))

        self.assertEqual(image.size[0], max(180, pixel_size.width))
        self.assertEqual(image.size[1], pixel_size.height)
        self.assertGreater(image.size[0], 50)
        self.assertGreater(image.size[1], 10)


class FontNameTest(FontComponentTestCase):
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
