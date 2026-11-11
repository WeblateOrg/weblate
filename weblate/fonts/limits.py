# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Work budgets shared by font checks and previews."""

from __future__ import annotations

from math import isfinite

from django.utils.translation import gettext

MAX_RENDER_DIMENSION = 2048
MAX_RENDER_FONT_SIZE = 256
MAX_RENDER_LINES = 64
MAX_RENDER_CHARACTERS = 16_000


class RenderLimitError(ValueError):
    def __init__(self) -> None:
        super().__init__(render_limit_message())


def render_limit_message() -> str:
    return gettext(
        "Font rendering limits exceeded: use at most 16,000 characters, 64 lines, 256 px fonts, and 2,048 px preview dimensions."
    )


def validate_render_text(text: str) -> None:
    if (
        len(text) > MAX_RENDER_CHARACTERS
        or text.replace("\r\n", "\n").replace("\r", "\n").count("\n")
        >= MAX_RENDER_LINES
    ):
        raise RenderLimitError


def validate_render_params(
    text: str,
    *,
    width: int,
    lines: int,
    size: int,
    spacing: float,
    surface_width: int | None = None,
    surface_height: int | None = None,
) -> None:
    validate_render_text(text)
    if (
        not 1 <= width <= MAX_RENDER_DIMENSION
        or not 1 <= lines <= MAX_RENDER_LINES
        or not 1 <= size <= MAX_RENDER_FONT_SIZE
        or abs(spacing) > MAX_RENDER_DIMENSION
        or not isfinite(spacing)
        or any(
            value is not None and not 1 <= value <= MAX_RENDER_DIMENSION
            for value in (surface_width, surface_height)
        )
    ):
        raise RenderLimitError
