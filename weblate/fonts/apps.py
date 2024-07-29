# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import CheckMessage, register

from weblate.utils.checks import weblate_check

from .utils import render_size

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@register
def check_fonts(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    """Check font rendering."""
    try:
        render_size(text="test")
    except Exception as error:
        return [weblate_check("weblate.C024", f"Could not use Pango: {error}")]
    return []


class FontsConfig(AppConfig):
    name = "weblate.fonts"
    label = "fonts"
    verbose_name = "Fonts"
