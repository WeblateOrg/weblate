# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin


class ScreenshotAdmin(WeblateModelAdmin):
    list_display = ["name", "translation"]
    search_fields = ["name", "image"]
    list_filter = [("translation__component", admin.RelatedOnlyFieldListFilter)]
    raw_id_fields = ("units",)
