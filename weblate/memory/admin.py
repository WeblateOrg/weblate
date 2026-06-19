# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from .models import Memory, MemoryScope, MemoryScopeMigrationState


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = (
        "source_language",
        "target_language",
        "source",
        "origin",
        "legacy_from_file",
        "legacy_shared",
    )
    search_fields = (
        "source_language__code",
        "target_language__code",
        "source",
        "target",
        "origin",
    )
    list_filter = (
        ("legacy_project", admin.RelatedOnlyFieldListFilter),
        "legacy_shared",
        "legacy_from_file",
    )


@admin.register(MemoryScope)
class MemoryScopeAdmin(admin.ModelAdmin):
    list_display = ("memory", "scope", "project", "workspace", "source_project", "user")
    list_filter = (
        "scope",
        ("project", admin.RelatedOnlyFieldListFilter),
        ("workspace", admin.RelatedOnlyFieldListFilter),
        ("source_project", admin.RelatedOnlyFieldListFilter),
    )


@admin.register(MemoryScopeMigrationState)
class MemoryScopeMigrationStateAdmin(admin.ModelAdmin):
    list_display = ("name", "last_memory_id", "completed", "updated")
