# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import Check


class CheckAdmin(WeblateModelAdmin):
    list_display = ["name", "unit", "dismissed"]
    search_fields = ["unit__source", "name"]
    list_filter = ["name", "dismissed"]


# Show some controls only in debug mode
if settings.DEBUG:
    admin.site.register(Check, CheckAdmin)
