# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import Workspace


@admin.register(Workspace)
class WorkspaceAdmin(WeblateModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
