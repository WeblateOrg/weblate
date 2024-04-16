# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import Agreement


@admin.register(Agreement)
class AgreementAdmin(WeblateModelAdmin):
    list_display = ["user", "tos", "timestamp", "address", "user_agent"]
    search_fields = ["user__username"]
    list_filter = ["tos"]
    date_hierarchy = "timestamp"
    ordering = ["user__username"]
