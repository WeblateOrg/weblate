# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.wladmin.models import WeblateModelAdmin


class SettingAdmin(WeblateModelAdmin):
    list_display = ("category", "name", "value")
    list_filter = ("category",)
    search_fields = ("name", "value")
