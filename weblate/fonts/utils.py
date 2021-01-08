#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Font handling wrapper."""


import os
from functools import lru_cache
from io import BytesIO
from tempfile import NamedTemporaryFile

import cairo
import gi
from django.conf import settings
from django.core.cache import cache
from django.utils.html import escape
from PIL import ImageFont

from weblate.utils.checks import weblate_check
from weblate.utils.data import data_dir

gi.require_version("PangoCairo", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Pango, PangoCairo  # noqa:E402,I001 isort:skip

FONTCONFIG_CONFIG = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <cachedir>{}</cachedir>
    <dir>{}</dir>
    <dir>{}</dir>
    <dir>{}</dir>
    <dir>{}</dir>
    <config>
        <rescan>
            <int>30</int>
        </rescan>
    </config>

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

</fontconfig>
"""

FONT_WEIGHTS = {
    "normal": Pango.Weight.NORMAL,
    "light": Pango.Weight.LIGHT,
    "bold": Pango.Weight.BOLD,
    "": None,
}


def configure_fontconfig():
    """Configures fontconfig to use custom configuration."""
    if getattr(configure_fontconfig, "is_configured", False):
        return

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
                os.path.join(settings.STATIC_ROOT, "font-source", "TTF"),
                os.path.join(settings.STATIC_ROOT, "font-dejavu"),
                os.path.join(settings.STATIC_ROOT, "font-droid"),
            )
        )

    # Inject into environment
    os.environ["FONTCONFIG_FILE"] = config_name

    configure_fontconfig.is_configured = True


def get_font_weight(weight):
    return FONT_WEIGHTS[weight]


@lru_cache(maxsize=512)
def render_size(font, weight, size, spacing, text, width=1000, lines=1, cache_key=None):
    """Check whether rendered text fits."""
    configure_fontconfig()

    # Setup Pango/Cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * 2, lines * size * 4)
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)

    # Load and configure font
    fontdesc = Pango.FontDescription.from_string(font)
    fontdesc.set_size(size * Pango.SCALE)
    if weight:
        fontdesc.set_weight(weight)
    layout.set_font_description(fontdesc)

    # This seems to be only way to set letter spacing
    # See https://stackoverflow.com/q/55533312/225718
    layout.set_markup(
        '<span letter_spacing="{}">{}</span>'.format(spacing, escape(text))
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
            cache.set(cache_key, buff.getvalue())

    return pixel_size, line_count


def check_render_size(font, weight, size, spacing, text, width, lines, cache_key=None):
    """Checks whether rendered text fits."""
    size, actual_lines = render_size(
        font, weight, size, spacing, text, width, lines, cache_key
    )
    return size.width <= width and actual_lines <= lines


def get_font_name(filelike):
    """Returns tuple of font family and style, for example ('Ubuntu', 'Regular')."""
    if not hasattr(filelike, "loaded_font"):
        # The tempfile creation is workaroud for Pillow crashing on invalid font
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


def check_fonts(app_configs=None, **kwargs):
    """Checks font rendering."""
    try:
        render_size("DejaVu Sans", Pango.Weight.NORMAL, 11, 0, "test")
        return []
    except Exception as error:
        return [weblate_check("weblate.C024", f"Failed to use Pango: {error}")]
