# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import Warning as DjangoWarning
from django.core.checks import register
from django.core.files.storage import default_storage

from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.core.checks import CheckMessage


@register
def check_screenshot_storage(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs: object,
) -> Iterable[CheckMessage]:
    """Check that screenshot storage does not overwrite existing files."""
    # django-storages S3 and Google Cloud Storage overwrite by default,
    # Azure uses a different option name
    for option in ("file_overwrite", "overwrite_files"):
        if getattr(default_storage, option, False):
            return [
                weblate_check(
                    "weblate.W053",
                    "The file storage overwrites existing files, so screenshots "
                    "with the same file name replace each other. "
                    f"Set {option} to false in the storage options.",
                    DjangoWarning,
                )
            ]
    return []


class ScreenshotsConfig(AppConfig):
    name = "weblate.screenshots"
    label = "screenshots"
    verbose_name = "Screenshots"

    def ready(self) -> None:
        super().ready()

        # Tesserocr imports cysignals, which has to register its signal handlers in
        # the main thread. Preload just cysignals to keep tesserocr itself lazy.
        import_module("cysignals")
