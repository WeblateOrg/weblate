# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from weblate.lang.models import Language, Plural
from weblate.wladmin.models import WeblateModelAdmin

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class PluralAdmin(admin.TabularInline):
    model = Plural
    extra = 0
    ordering = ["source"]


@admin.register(Language)
class LanguageAdmin(WeblateModelAdmin):
    list_display = ["name", "code", "direction"]
    search_fields = ["name", "code"]
    list_filter = ("direction",)
    inlines = [PluralAdmin]
    ordering = ["name"]

    def save_related(
        self, request: AuthenticatedHttpRequest, form, formsets, change
    ) -> None:
        super().save_related(request, form, formsets, change)
        lang = form.instance

        if lang.plural_set.exists():
            return

        # Automatically create plurals if language does not have one
        try:
            baselang = Language.objects.get(code=lang.base_code)
            baseplural = baselang.plural
            lang.plural_set.create(
                source=Plural.SOURCE_DEFAULT,
                number=baseplural.number,
                formula=baseplural.formula,
            )
        except (Language.DoesNotExist, IndexError):
            lang.plural_set.create(
                source=Plural.SOURCE_DEFAULT, number=2, formula="n != 1"
            )
