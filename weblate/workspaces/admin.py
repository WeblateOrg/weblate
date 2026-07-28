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

    def get_deleted_objects(self, objs, request):
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = super().get_deleted_objects(objs, request)
        # Workspace teams can not be deleted directly, but are owned by the
        # workspace and should be removed together with it.
        perms_needed.discard("Group")
        return deleted_objects, model_count, perms_needed, protected
