# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from importlib import import_module

from django.apps import AppConfig


class ScreenshotsConfig(AppConfig):
    name = "weblate.screenshots"
    label = "screenshots"
    verbose_name = "Screenshots"

    def ready(self) -> None:
        super().ready()

        # Tesserocr imports cysignals, which has to register its signal handlers in
        # the main thread. Preload just cysignals to keep tesserocr itself lazy.
        import_module("cysignals")
