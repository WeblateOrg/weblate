# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(WeblateModelAdmin):
    list_display = ("category", "name", "value")
    list_filter = ("category",)
    search_fields = ("name", "value")
