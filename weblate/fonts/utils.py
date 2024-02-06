# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Font handling wrapper."""

from __future__ import annotations

import os
from functools import cache, lru_cache
from io import BytesIO
from tempfile import NamedTemporaryFile
from typing import NamedTuple

import cairo
import gi
from django.conf import settings
from django.core.cache import cache as django_cache
from django.utils.html import format_html
from PIL import ImageFont

from weblate.utils.data import data_dir

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
def configure_fontconfig():
    """Configures fontconfig to use custom configuration."""
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
                os.path.join(settings.STATIC_ROOT, "vendor", "font-source", "TTF"),
                os.path.join(settings.STATIC_ROOT, "vendor", "font-kurinto"),
            )
        )

    # Inject into environment
    os.environ["FONTCONFIG_FILE"] = config_name


def get_font_weight(weight: str) -> int:
    return FONT_WEIGHTS[weight]


@lru_cache(maxsize=512)
def render_size(
    text: str,
    *,
    font: str = "Kurinto Sans",
    weight: int = Pango.Weight.NORMAL,
    size: int = 11,
    spacing: int = 0,
    width: int = 1000,
    lines: int = 1,
    cache_key: str | None = None,
) -> tuple[Dimensions, int]:
    """Check whether rendered text fits."""
    configure_fontconfig()

    # Setup Pango/Cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * 2, lines * size * 4)
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)

    # Load and configure font
    fontdesc = Pango.FontDescription.from_string(font)
    fontdesc.set_absolute_size(size * Pango.SCALE)
    if weight:
        fontdesc.set_weight(weight)
    layout.set_font_description(fontdesc)

    # This seems to be only way to set letter spacing
    # See https://stackoverflow.com/q/55533312/225718
    layout.set_markup(
        format_html(
            '<span letter_spacing="{}">{}</span>',
            spacing,
            text,
        )
    )

    # Set width and line wrapping
    layout.set_width(width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD)

    # Calculate dimensions
    line_count = layout.get_line_count()
    pixel_size = layout.get_pixel_size()

    # Show text
    PangoCairo.show_layout(context, layout)

    # Render box around desired size
    expected_height = lines * pixel_size.height / line_count
    context.new_path()
    context.set_source_rgb(0.8, 0.8, 0.8)
    context.set_line_width(1)
    context.move_to(1, 1)
    context.line_to(width, 1)
    context.line_to(width, expected_height)
    context.line_to(1, expected_height)
    context.line_to(1, 1)
    context.stroke()

    # Render box about actual size
    context.new_path()
    if pixel_size.width > width or line_count > lines:
        context.set_source_rgb(246 / 255, 102 / 255, 76 / 255)
    else:
        context.set_source_rgb(0.4, 0.4, 0.4)
    context.set_line_width(1)
    context.move_to(1, 1)
    context.line_to(pixel_size.width, 1)
    context.line_to(pixel_size.width, pixel_size.height)
    context.line_to(1, pixel_size.height)
    context.line_to(1, 1)
    context.stroke()

    if cache_key:
        with BytesIO() as buff:
            surface.write_to_png(buff)
            django_cache.set(cache_key, buff.getvalue())

    return pixel_size, line_count


def check_render_size(
    *,
    font: str,
    weight: int,
    size: int,
    spacing: int,
    text: str,
    width: int,
    lines: int,
    cache_key: str | None = None,
) -> bool:
    """Checks whether rendered text fits."""
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
    """Returns tuple of font family and style, for example ('Ubuntu', 'Regular')."""
    if not hasattr(filelike, "loaded_font"):
        # The tempfile creation is workaround for Pillow crashing on invalid font
        # see https://github.com/python-pillow/Pillow/issues/3853
        # Once this is fixed, it should be possible to directly operate on filelike
        temp = NamedTemporaryFile(delete=False)
        try:
            temp.write(filelike.read())
            filelike.seek(0)
            temp.close()
            filelike.loaded_font = ImageFont.truetype(temp.name)
        finally:
            os.unlink(temp.name)
    return filelike.loaded_font.getname()
