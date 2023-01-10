# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.wladmin.models import WeblateModelAdmin


class CheckAdmin(WeblateModelAdmin):
    list_display = ["name", "unit", "dismissed"]
    search_fields = ["unit__source", "name"]
    list_filter = ["name", "dismissed"]
