# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import Warning as DjangoWarning
from django.core.checks import register

from weblate.utils.checks import weblate_check

from .storage import font_storage
from .utils import render_size

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.core.checks import CheckMessage


@register
def check_fonts(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs: object,
) -> Iterable[CheckMessage]:
    """Check font rendering."""
    try:
        render_size(text="test", use_cache=False)
    except Exception as error:
        return [weblate_check("weblate.C024", f"Could not use Matplotlib: {error}")]
    return []


@register
def check_font_storage(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs: object,
) -> Iterable[CheckMessage]:
    """Check that font storage does not overwrite existing files."""
    # django-storages S3 and Google Cloud Storage overwrite by default,
    # Azure uses a different option name
    for option in ("file_overwrite", "overwrite_files"):
        if getattr(font_storage, option, False):
            return [
                weblate_check(
                    "weblate.W054",
                    "The font storage overwrites existing files, so fonts "
                    "with the same file name replace each other. "
                    f"Set {option} to false in the storage options.",
                    DjangoWarning,
                )
            ]
    return []


class FontsConfig(AppConfig):
    name = "weblate.fonts"
    label = "fonts"
    verbose_name = "Fonts"
