# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from .models import Memory


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = [
        "source_language",
        "target_language",
        "source",
        "origin",
        "from_file",
        "shared",
    ]
    search_fields = [
        "source_language__code",
        "target_language__code",
        "source",
        "target",
        "origin",
    ]
    list_filter = [("project", admin.RelatedOnlyFieldListFilter), "shared", "from_file"]
