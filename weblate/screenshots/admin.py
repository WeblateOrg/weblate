# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import Screenshot


@admin.register(Screenshot)
class ScreenshotAdmin(WeblateModelAdmin):
    list_display = ("name", "translation")
    search_fields = (
        "name",
        "image",
        "translation__component__name",
        "translation__component__slug",
        "translation__component__project__name",
        "translation__component__project__slug",
    )
    raw_id_fields = ("units",)
