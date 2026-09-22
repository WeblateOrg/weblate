# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.apps import AppConfig


class KotlinSDKConfig(AppConfig):
    name = "weblate.kotlin_sdk"
    label = "kotlin_sdk"
    verbose_name = "Kotlin SDK"

    def ready(self) -> None:
        from django.db.models.signals import post_delete  # ruff: ignore[import-outside-top-level]

        from weblate.kotlin_sdk.signals import remove_publication  # ruff: ignore[import-outside-top-level]

        post_delete.connect(remove_publication, sender="addons.Addon")
