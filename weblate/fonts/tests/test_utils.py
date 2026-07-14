# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for fonts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.base import File
from django.test import SimpleTestCase
from PIL import Image

from weblate.fonts.render import (
    _get_layout_font,
    _layout_item_cluster_indices,
    _layout_items,
    _load_uploaded_font_files,
    _register_uploaded_font_files,
    create_figure,
    draw_text,
    figure_to_png,
    get_font_properties,
    measure_line,
    split_explicit_lines,
    wrap_text,
)
from weblate.fonts.tests.utils import (
    FONT,
    FONT_BOLD,
    FONT_NAME,
    FONT_SOURCE_ITALIC,
    FONT_SOURCE_REGULAR,
    FontComponentTestCase,
)
from weblate.fonts.utils import (
    MAX_RENDERED_TEXT_OVERFLOW,
    _render_size,
    check_render_size,
    get_font_name,
    get_font_weight,
)


class RenderTest(SimpleTestCase):
    def test_uploaded_font_caches_are_bounded(self) -> None:
        self.assertEqual(
            _load_uploaded_font_files.cache_parameters()["maxsize"],
            32,
        )
        self.assertEqual(
            _register_uploaded_font_files.cache_parameters()["maxsize"],
            32,
        )

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

    def test_render_single_line_does_not_wrap(self) -> None:
        pixel_size, line_count, _ = _render_size(
            text="Hello World!",
            font="sans",
            weight=get_font_weight("normal"),
            size=20,
            spacing=0,
            width=100,
            lines=1,
        )

        self.assertGreater(pixel_size.width, 100)
        self.assertEqual(line_count, 1)

    def test_render_multiline_wraps(self) -> None:
        pixel_size, line_count, _ = _render_size(
            text="Hello World!",
            font="sans",
            weight=get_font_weight("normal"),
            size=20,
            spacing=0,
            width=100,
            lines=2,
        )

        self.assertLessEqual(pixel_size.width, 100)
        self.assertEqual(line_count, 2)

    def test_render_multiline_wraps_cjk(self) -> None:
        pixel_size, line_count, _ = _render_size(
            text="你好世界你好世界",
            font="sans",
            size=20,
            width=50,
            lines=2,
        )

        self.assertLessEqual(pixel_size.width, 50)
        self.assertEqual(line_count, 4)

    def test_render_multiline_wraps_hangul(self) -> None:
        pixel_size, line_count, _ = _render_size(
            text="한글한글한글한글",
            font="sans",
            size=20,
            width=50,
            lines=2,
        )

        self.assertLessEqual(pixel_size.width, 50)
        self.assertEqual(line_count, 4)

    def test_render_multiline_wraps_at_soft_hyphen(self) -> None:
        font_properties = get_font_properties("sans", size=20)

        wrapped = wrap_text("a foo\N{SOFT HYPHEN}bar", 45, font_properties)

        self.assertEqual(wrapped, ["a", "foo\N{HYPHEN}", "bar"])
        self.assertTrue(
            all(measure_line(line, font_properties)[0] <= 45 for line in wrapped)
        )

    def test_render_multiline_hides_unselected_soft_hyphen(self) -> None:
        font_properties = get_font_properties("sans", size=20)

        self.assertEqual(
            wrap_text("foo\N{SOFT HYPHEN}bar", 60, font_properties),
            ["foobar"],
        )

    def test_render_multiline_preserves_leading_whitespace(self) -> None:
        font_properties = get_font_properties("sans", size=20)

        wrapped = wrap_text("  Hello world", 200, font_properties)

        self.assertEqual(wrapped, ["  Hello world"])
        self.assertGreater(
            measure_line(wrapped[0], font_properties)[0],
            measure_line("Hello world", font_properties)[0],
        )

    def test_render_multiline_preserves_no_break_space(self) -> None:
        pixel_size, line_count, _ = _render_size(
            text="Hello\N{NO-BREAK SPACE}world",
            font="sans",
            size=20,
            width=50,
            lines=2,
        )

        self.assertGreater(pixel_size.width, 50)
        self.assertEqual(line_count, 1)

    def test_render_normalizes_crlf_line_breaks(self) -> None:
        crlf_size, crlf_lines, crlf_buffer = _render_size(
            text="First\r\nSecond\r\n",
            font="sans",
            size=20,
            lines=1,
            needs_output=True,
        )
        lf_size, lf_lines, _ = _render_size(
            text="First\nSecond\n",
            font="sans",
            size=20,
            lines=1,
        )

        self.assertEqual(
            split_explicit_lines("First\r\nSecond\r\n"), ["First", "Second", ""]
        )
        self.assertEqual(crlf_size, lf_size)
        self.assertEqual(crlf_lines, lf_lines)
        self.assertEqual(crlf_lines, 3)
        self.assertEqual(Image.open(BytesIO(crlf_buffer)).format, "PNG")

    def test_render_dollar_signs_as_literal_text(self) -> None:
        pixel_size, line_count, buffer = _render_size(
            text="$x_{$",
            font="sans",
            size=20,
            needs_output=True,
        )

        self.assertGreater(pixel_size.width, 0)
        self.assertEqual(line_count, 1)
        self.assertEqual(Image.open(BytesIO(buffer)).format, "PNG")

    def test_render_complex_bidirectional_text(self) -> None:
        text = "English العربية עברית 123"
        font_properties = get_font_properties("sans", size=20)
        layout = _layout_items(text, _get_layout_font(font_properties))
        pixel_size, line_count, buffer = _render_size(
            text=text,
            font="sans",
            weight=get_font_weight("normal"),
            size=20,
            width=400,
            lines=1,
            needs_output=True,
        )

        image = Image.open(BytesIO(buffer))

        self.assertGreater(pixel_size.width, 0)
        self.assertGreater(pixel_size.height, 0)
        self.assertEqual(line_count, 1)
        self.assertEqual(image.format, "PNG")
        self.assertIsNotNone(layout)
        self.assertEqual(
            [item.char for item in layout[-7:]],
            list(reversed("العربية")),
        )

    def test_render_shapes_complex_scripts(self) -> None:
        font_properties = get_font_properties("sans", size=30)

        for text in ("العربية", "कर्म"):
            shaped_width = measure_line(text, font_properties)[0]
            isolated_width = sum(
                measure_line(character, font_properties)[0] for character in text
            )

            self.assertLess(shaped_width, isolated_width)

    def test_render_letter_spacing(self) -> None:
        unspaced, _, _ = _render_size(
            text="office",
            font="sans",
            size=20,
            spacing=0,
        )
        spaced, _, buffer = _render_size(
            text="office",
            font="sans",
            size=20,
            spacing=3,
            needs_output=True,
        )

        self.assertGreater(spaced.width, unspaced.width)
        self.assertEqual(Image.open(BytesIO(buffer)).format, "PNG")

    def test_render_letter_spacing_preserves_grapheme_clusters(self) -> None:
        text = "நிx"
        spacing = 5
        font_properties = get_font_properties("sans", size=30)
        font = _get_layout_font(font_properties)
        items = _layout_items(
            text,
            font,
            features=("-liga", "-clig"),
        )

        self.assertIsNotNone(items)
        self.assertEqual(_layout_item_cluster_indices(items, font), [0, 0, 1])
        self.assertAlmostEqual(
            measure_line(text, font_properties, spacing=spacing)[0]
            - measure_line(text, font_properties)[0],
            spacing,
            delta=0.25,
        )

    def test_render_uploaded_font_uses_sibling_bold_face(self) -> None:
        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            bold_path = Path(temp_directory) / "bold.ttf"
            copyfile(str(FONT), regular_path)
            synthetic_bold = measure_line(
                "mmmm WWWW",
                get_font_properties(str(regular_path), size=30, weight=700),
            )[0]
            copyfile(str(FONT_BOLD), bold_path)
            (Path(temp_directory) / "unrelated.ttf").write_text(
                "not a font", encoding="utf-8"
            )

            regular = measure_line(
                "mmmm WWWW",
                get_font_properties(
                    str(regular_path),
                    size=30,
                    weight=400,
                    font_siblings=(str(bold_path),),
                ),
            )[0]
            bold = measure_line(
                "mmmm WWWW",
                get_font_properties(
                    str(regular_path),
                    size=30,
                    weight=700,
                    font_siblings=(str(bold_path),),
                ),
            )[0]

        expected_regular = measure_line(
            "mmmm WWWW",
            get_font_properties("Kurinto Sans", size=30, weight=400),
        )[0]
        expected_bold = measure_line(
            "mmmm WWWW",
            get_font_properties("Kurinto Sans", size=30, weight=700),
        )[0]
        self.assertEqual(regular, expected_regular)
        self.assertEqual(bold, expected_bold)
        self.assertNotEqual(bold, synthetic_bold)
        self.assertNotEqual(bold, regular)

    def test_render_uploaded_font_preserves_selected_bold_face(self) -> None:
        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            bold_path = Path(temp_directory) / "bold.ttf"
            copyfile(str(FONT), regular_path)
            copyfile(str(FONT_BOLD), bold_path)

            selected = measure_line(
                "mmmm WWWW",
                get_font_properties(
                    str(bold_path),
                    size=30,
                    weight=None,
                    font_siblings=(str(regular_path),),
                ),
            )[0]

        expected_regular = measure_line(
            "mmmm WWWW",
            get_font_properties("Kurinto Sans", size=30, weight=400),
        )[0]
        expected_bold = measure_line(
            "mmmm WWWW",
            get_font_properties("Kurinto Sans", size=30, weight=700),
        )[0]
        self.assertEqual(selected, expected_bold)
        self.assertNotEqual(selected, expected_regular)

    def test_render_uploaded_font_preserves_selected_italic_face(self) -> None:
        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            italic_path = Path(temp_directory) / "italic.ttf"
            copyfile(str(FONT_SOURCE_REGULAR), regular_path)
            copyfile(str(FONT_SOURCE_ITALIC), italic_path)

            properties = get_font_properties(str(italic_path), size=30, weight=None)

        self.assertEqual(properties.get_style(), "italic")

    def test_render_uploaded_font_synthesizes_missing_bold_face(self) -> None:
        def render_ink(font_properties) -> int:
            figure = create_figure(300, 80)
            draw_text(
                figure,
                0,
                50,
                "Synthetic bold",
                font_properties=font_properties,
                color=(0, 0, 0),
                verticalalignment="baseline",
            )
            image = Image.open(BytesIO(figure_to_png(figure)))
            return sum(
                value * count
                for value, count in enumerate(image.getchannel("A").histogram())
            )

        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            copyfile(str(FONT), regular_path)
            regular_properties = get_font_properties(
                str(regular_path), size=30, weight=400
            )
            bold_properties = get_font_properties(
                str(regular_path), size=30, weight=700
            )

            regular_width = measure_line("Synthetic bold", regular_properties)[0]
            bold_width = measure_line("Synthetic bold", bold_properties)[0]
            regular_ink = render_ink(regular_properties)
            bold_ink = render_ink(bold_properties)

        self.assertGreater(bold_width, regular_width)
        self.assertGreater(bold_ink, regular_ink)

    def test_render_uploaded_font_ignores_missing_sibling(self) -> None:
        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            missing_path = Path(temp_directory) / "missing.ttf"
            copyfile(str(FONT), regular_path)

            width = measure_line(
                "Available font",
                get_font_properties(
                    str(regular_path),
                    size=30,
                    weight=400,
                    font_siblings=(str(missing_path),),
                ),
            )[0]

        self.assertGreater(width, 0)

    def test_render_uploaded_font_ignores_invalid_sibling(self) -> None:
        with TemporaryDirectory() as temp_directory:
            regular_path = Path(temp_directory) / "regular.ttf"
            invalid_path = Path(temp_directory) / "invalid.ttf"
            copyfile(str(FONT), regular_path)
            invalid_path.write_text("not a font", encoding="utf-8")

            width = measure_line(
                "Available font",
                get_font_properties(
                    str(regular_path),
                    size=30,
                    weight=400,
                    font_siblings=(str(invalid_path),),
                ),
            )[0]

        self.assertGreater(width, 0)

    def test_render_uploaded_font_rejects_invalid_selected_font(self) -> None:
        with TemporaryDirectory() as temp_directory:
            invalid_path = Path(temp_directory) / "invalid.ttf"
            invalid_path.write_text("not a font", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                get_font_properties(str(invalid_path), size=30, weight=400)

    def test_render_letter_spacing_uses_public_fallback(self) -> None:
        font_properties = get_font_properties("sans", size=20)
        figure = create_figure(200, 50)

        with patch("weblate.fonts.render._text_helpers", None):
            spaced_width = measure_line("Fallback", font_properties, spacing=2)[0]
            draw_text(
                figure,
                0,
                0,
                "Fallback",
                font_properties=font_properties,
                color=(0, 0, 0),
                spacing=2,
            )

        self.assertGreater(
            spaced_width,
            measure_line("Fallback", font_properties)[0],
        )
        self.assertEqual(Image.open(BytesIO(figure_to_png(figure))).format, "PNG")

    def test_render_is_safe_from_multiple_threads(self) -> None:
        def render(index: int) -> tuple[int, str]:
            dimensions, _, buffer = _render_size(
                text=f"Thread {index}: العربية",
                font="sans",
                size=16,
                spacing=index % 2,
                needs_output=True,
            )
            return dimensions.width, Image.open(BytesIO(buffer)).format or ""

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(render, range(8)))

        self.assertTrue(all(width > 0 for width, _format in results))
        self.assertTrue(all(image_format == "PNG" for _width, image_format in results))

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
        pixel_size, _, buffer = _render_size(
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

        self.assertEqual(image.size[0], max(180, pixel_size.width))
        self.assertGreaterEqual(image.size[1], pixel_size.height)
        self.assertTrue(
            any(
                pixels[x, y][0] > 200
                and pixels[x, y][1] < 160
                and pixels[x, y][2] < 160
                for x in range(cropped.width)
                for y in range(cropped.height)
            )
        )

    def test_render_output_width_is_capped(self) -> None:
        pixel_size, line_count, buffer = _render_size(
            text="Hello World! " * 1000,
            font="sans",
            weight=get_font_weight("normal"),
            size=20,
            spacing=0,
            width=100,
            lines=1,
            needs_output=True,
        )

        image = Image.open(BytesIO(buffer))

        self.assertGreater(pixel_size.width, image.width)
        self.assertEqual(line_count, 1)
        self.assertEqual(image.width, 100 + MAX_RENDERED_TEXT_OVERFLOW)

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
