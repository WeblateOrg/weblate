# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Font handling wrapper."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from math import ceil
from typing import TYPE_CHECKING, NamedTuple

from django.core.cache import cache as django_cache
from PIL import ImageFont

from weblate.fonts.render import (
    create_clip_box,
    create_figure,
    draw_outline_rectangle,
    draw_text,
    figure_to_png,
    get_font_properties,
    measure_multiline,
    rendering_lock,
    split_explicit_lines,
    wrap_text,
)
from weblate.utils.files import read_file_bytes
from weblate.utils.hash import calculate_hash

if TYPE_CHECKING:
    from django.core.files.base import File
    from django.db.models.fields.files import FieldFile


class Dimensions(NamedTuple):
    width: int
    height: int


MAX_RENDERED_TEXT_OVERFLOW = 1000

FONT_WEIGHTS = {
    "normal": 400,
    "light": 300,
    "bold": 700,
    "": None,
}


def get_font_weight(weight: str) -> int | None:
    return FONT_WEIGHTS[weight]


@lru_cache(maxsize=32)
def _render_size(
    text: str,
    *,
    font: str = "Kurinto Sans",
    font_siblings: tuple[str, ...] = (),
    weight: int | None = 400,
    size: int = 11,
    spacing: float = 0,
    width: int = 1000,
    lines: int = 1,
    needs_output: bool = False,
    surface_height: int | None = None,
    surface_width: int | None = None,
) -> tuple[Dimensions, int, bytes]:
    """Check whether rendered text fits."""
    if surface_height is None:
        surface_height = int(lines * size * 1.5)
    if surface_width is None:
        surface_width = width

    font_properties = get_font_properties(
        font,
        size=size,
        weight=weight,
        font_siblings=font_siblings,
    )
    with rendering_lock():
        rendered_lines = (
            split_explicit_lines(text)
            if lines == 1
            else wrap_text(text, width, font_properties, spacing=spacing)
        )
        measured_width, measured_height = measure_multiline(
            rendered_lines, font_properties, spacing=spacing
        )
        pixel_size = Dimensions(measured_width, measured_height)
        line_count = len(rendered_lines)

        if not needs_output:
            return pixel_size, line_count, b""

        surface_height = max(surface_height, pixel_size.height)
        surface_width = max(
            width,
            surface_width,
            min(pixel_size.width, width + MAX_RENDERED_TEXT_OVERFLOW),
        )
        expected_height = ceil(lines * pixel_size.height / line_count)
        overflow = pixel_size.width > width or line_count > lines
        figure = create_figure(surface_width, surface_height, facecolor=(0.8, 0.8, 0.8))
        rendered_text = "\n".join(rendered_lines)

        if overflow:
            draw_text(
                figure,
                0,
                0,
                rendered_text,
                font_properties=font_properties,
                color=(246 / 255, 102 / 255, 76 / 255),
                spacing=spacing,
            )

        clip_box = create_clip_box(
            0, surface_height - expected_height, width, expected_height
        )
        draw_text(
            figure,
            0,
            0,
            rendered_text,
            font_properties=font_properties,
            color=(0, 0, 0),
            spacing=spacing,
            clip_box=clip_box,
        )
        draw_outline_rectangle(
            figure,
            1,
            1,
            width - 2,
            expected_height - 2,
            color=(0.1, 0.1, 0.1),
        )
        if overflow:
            draw_outline_rectangle(
                figure,
                1,
                1,
                pixel_size.width - 2,
                pixel_size.height - 2,
                color=(246 / 255, 102 / 255, 76 / 255),
            )
        buffer = figure_to_png(figure)

    return pixel_size, line_count, buffer


def render_size(
    text: str,
    *,
    font: str = "Kurinto Sans",
    font_siblings: tuple[str, ...] = (),
    weight: int | None = 400,
    size: int = 11,
    spacing: float = 0,
    width: int = 1000,
    lines: int = 1,
    cache_key: str | None = None,
    surface_height: int | None = None,
    surface_width: int | None = None,
    use_cache: bool = True,
) -> tuple[Dimensions, int]:
    font_hash = calculate_hash("\0".join((font, *font_siblings)))
    render_cache_key = f"render:{calculate_hash(text)}:{font_hash}:{int(weight) if weight is not None else ''}:{size}:{spacing}:{width}:{lines}:{cache_key}:{surface_height}:{surface_width}"
    if use_cache:
        cached: tuple[Dimensions, int] | None = django_cache.get(render_cache_key)
        if cached and (cache_key is None or django_cache.get(cache_key)):
            return cached
    pixel_size, line_count, buffer = _render_size(
        text,
        font=font,
        font_siblings=font_siblings,
        weight=weight,
        size=size,
        spacing=spacing,
        width=width,
        lines=lines,
        needs_output=cache_key is not None,
        surface_height=surface_height,
        surface_width=surface_width,
    )
    if cache_key:
        # Longer expiry for rendered results so that it can be recalculated
        django_cache.set(cache_key, buffer, timeout=4200)
    result = pixel_size, line_count
    django_cache.set(render_cache_key, result, timeout=3600)
    return result


def check_render_size(
    *,
    font: str,
    font_siblings: tuple[str, ...] = (),
    weight: int | None,
    size: int,
    spacing: float,
    text: str,
    width: int,
    lines: int,
    cache_key: str | None = None,
) -> bool:
    """Check whether rendered text fits."""
    rendered_size, actual_lines = render_size(
        font=font,
        font_siblings=font_siblings,
        weight=weight,
        size=size,
        spacing=spacing,
        text=text,
        width=width,
        lines=lines,
        cache_key=cache_key,
    )
    return rendered_size.width <= width and actual_lines <= lines


def get_font_name(filelike: FieldFile | File) -> tuple[str, str]:
    """Return tuple of font family and style, for example ('Ubuntu', 'Regular')."""
    # Parse fonts from in-memory bytes so Pillow does not keep the original
    # file descriptor alive after validation.
    family, style = ImageFont.truetype(BytesIO(read_file_bytes(filelike))).getname()
    if family is None or style is None:
        msg = "Font does not provide family and style names"
        raise OSError(msg)
    return family, style
