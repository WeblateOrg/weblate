# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Font handling wrapper."""

from __future__ import annotations

import os
from functools import cache, lru_cache
from io import BytesIO
from typing import NamedTuple

import cairo
import gi
from django.core.cache import cache as django_cache

from weblate.utils.data import data_dir
from weblate.utils.icons import find_static_file

gi.require_version("PangoCairo", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402


class Dimensions(NamedTuple):
    width: int
    height: int


FONTCONFIG_CONFIG = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <cachedir>{}</cachedir>
    <dir>{}</dir>
    <dir>{}</dir>
    <dir>{}</dir>
    <config>
        <rescan>
            <int>30</int>
        </rescan>
    </config>

    <alias>
        <family>sans-serif</family>
        <prefer>
            <family>Source Sans 3</family>
            <family>Kurinto Sans</family>
        </prefer>
    </alias>

    <alias>
        <family>Source Sans 3</family>
        <default><family>sans-serif</family></default>
    </alias>

    <alias>
        <family>Kurinto Sans</family>
        <default><family>sans-serif</family></default>
    </alias>

    <!--
     Synthetic emboldening for fonts that do not have bold face available
    -->
    <match target="font">
        <test name="weight" compare="less_eq">
            <const>medium</const>
        </test>
        <test target="pattern" name="weight" compare="more_eq">
            <const>bold</const>
        </test>
        <edit name="embolden" mode="assign">
            <bool>true</bool>
        </edit>
        <edit name="weight" mode="assign">
            <const>bold</const>
        </edit>
    </match>
    <!--
      Enable slight hinting for better sub-pixel rendering
    -->
    <match target="pattern">
      <edit name="hintstyle" mode="append"><const>hintslight</const></edit>
    </match>
</fontconfig>
"""

FONT_WEIGHTS = {
    "normal": Pango.Weight.NORMAL,
    "light": Pango.Weight.LIGHT,
    "bold": Pango.Weight.BOLD,
    "": None,
}


@cache
def configure_fontconfig() -> None:
    """Configure fontconfig to use custom configuration."""
    fonts_dir = data_dir("fonts")
    config_name = os.path.join(fonts_dir, "fonts.conf")

    if not os.path.exists(fonts_dir):
        os.makedirs(fonts_dir)

    # Generate the configuration
    with open(config_name, "w") as handle:
        handle.write(
            FONTCONFIG_CONFIG.format(
                data_dir("cache", "fonts"),
                fonts_dir,
                os.path.dirname(
                    find_static_file(
                        "js/vendor/fonts/font-source/TTF/SourceSans3-Regular.ttf"
                    )
                ),
                os.path.dirname(
                    find_static_file("vendor/font-kurinto/KurintoSans-Rg.ttf")
                ),
            )
        )

    # Inject into environment
    os.environ["FONTCONFIG_FILE"] = config_name


def get_font_weight(weight: str) -> int:
    return FONT_WEIGHTS[weight]


@lru_cache(maxsize=512)
def _render_size(
    text: str,
    *,
    font: str = "Kurinto Sans",
    weight: int | None = Pango.Weight.NORMAL,
    size: int = 11,
    spacing: int = 0,
    width: int = 1000,
    lines: int = 1,
    cache_key: str | None = None,
    surface_height: int | None = None,
    surface_width: int | None = None,
) -> tuple[Dimensions, int, bytes]:
    """Check whether rendered text fits."""
    configure_fontconfig()

    # Setup Pango/Cairo
    if surface_height is None:
        surface_height = int(lines * size * 1.5)
    if surface_width is None:
        surface_width = width
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, surface_width, surface_height)
    context = cairo.Context(surface)

    layout = PangoCairo.create_layout(context)

    # Load and configure font
    fontdesc = Pango.FontDescription.from_string(font)
    fontdesc.set_absolute_size(size * Pango.SCALE)
    if weight:
        fontdesc.set_weight(weight)
    layout.set_font_description(fontdesc)

    # Configure spacing
    if spacing:
        letter_spacing_attr = Pango.attr_letter_spacing_new(Pango.SCALE * spacing)
        attr_list = Pango.AttrList()
        attr_list.insert(letter_spacing_attr)
        layout.set_attributes(attr_list)

    # Set the actual text
    layout.set_text(text)

    # Set width and line wrapping
    layout.set_width(width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD)

    # Calculate dimensions
    line_count = layout.get_line_count()
    pixel_size = layout.get_pixel_size()

    buffer = b""

    if cache_key:
        # Adjust surface dimensions if we're actually rendering
        if pixel_size.height > surface_height or pixel_size.width > surface_width:
            return _render_size(
                text,
                font=font,
                weight=weight,
                size=size,
                spacing=spacing,
                width=width,
                lines=lines,
                cache_key=cache_key,
                surface_height=pixel_size.height,
                surface_width=pixel_size.width,
            )

        # Render background
        context.save()
        # This matches .img-check CSS style
        context.set_source_rgb(0.8, 0.8, 0.8)
        context.paint()
        context.restore()

        # Show text
        PangoCairo.show_layout(context, layout)

        # Render box around desired size
        expected_height = lines * pixel_size.height / line_count
        context.new_path()
        context.set_source_rgb(0.1, 0.1, 0.1)
        context.set_line_width(1)
        context.move_to(1, 1)
        context.line_to(width - 1, 1)
        context.line_to(width - 1, expected_height - 1)
        context.line_to(1, expected_height - 1)
        context.line_to(1, 1)
        context.stroke()

        # Render box about actual size if it does not fit
        if pixel_size.width > width or line_count > lines:
            context.new_path()
            context.set_source_rgb(246 / 255, 102 / 255, 76 / 255)
            context.set_line_width(1)
            context.move_to(1, 1)
            context.line_to(pixel_size.width - 1, 1)
            context.line_to(pixel_size.width - 1, pixel_size.height - 1)
            context.line_to(1, pixel_size.height - 1)
            context.line_to(1, 1)
            context.stroke()

        with BytesIO() as buff:
            surface.write_to_png(buff)
            buffer = buff.getvalue()

    return pixel_size, line_count, buffer


def render_size(
    text: str,
    *,
    font: str = "Kurinto Sans",
    weight: int | None = Pango.Weight.NORMAL,
    size: int = 11,
    spacing: int = 0,
    width: int = 1000,
    lines: int = 1,
    cache_key: str | None = None,
    surface_height: int | None = None,
    surface_width: int | None = None,
) -> tuple[Dimensions, int]:
    pixel_size, line_count, buffer = _render_size(
        text,
        font=font,
        size=size,
        spacing=spacing,
        width=width,
        lines=lines,
        cache_key=cache_key,
        surface_height=surface_height,
        surface_width=surface_width,
    )
    if cache_key:
        django_cache.set(cache_key, buffer)
    return pixel_size, line_count


def check_render_size(
    *,
    font: str,
    weight: int | None,
    size: int,
    spacing: int,
    text: str,
    width: int,
    lines: int,
    cache_key: str | None = None,
) -> bool:
    """Check whether rendered text fits."""
    rendered_size, actual_lines = render_size(
        font=font,
        weight=weight,
        size=size,
        spacing=spacing,
        text=text,
        width=width,
        lines=lines,
        cache_key=cache_key,
    )
    return rendered_size.width <= width and actual_lines <= lines


def get_font_name(filelike):
    """Return tuple of font family and style, for example ('Ubuntu', 'Regular')."""
    from PIL import ImageFont

    if not hasattr(filelike, "loaded_font"):
        filelike.loaded_font = ImageFont.truetype(filelike)
    return filelike.loaded_font.getname()
