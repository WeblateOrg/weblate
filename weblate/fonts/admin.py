# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.fonts.models import Font, FontGroup, FontOverride
from weblate.wladmin.models import WeblateModelAdmin


@admin.register(Font)
class FontAdmin(WeblateModelAdmin):
    list_display = ["family", "style", "project", "user"]
    search_fields = ["family", "style"]
    list_filter = [("project", admin.RelatedOnlyFieldListFilter)]
    ordering = ["family", "style"]


class InlineFontOverrideAdmin(admin.TabularInline):
    model = FontOverride
    extra = 0


@admin.register(FontGroup)
class FontGroupAdmin(WeblateModelAdmin):
    list_display = ["name", "font", "project"]
    search_fields = ["name", "font__family"]
    list_filter = [("project", admin.RelatedOnlyFieldListFilter)]
    ordering = ["name"]
    inlines = [InlineFontOverrideAdmin]
