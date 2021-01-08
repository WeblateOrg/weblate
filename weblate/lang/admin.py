#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.contrib import admin

from weblate.lang.models import Language, Plural
from weblate.wladmin.models import WeblateModelAdmin


class PluralAdmin(admin.TabularInline):
    model = Plural
    extra = 0
    ordering = ["source"]


class LanguageAdmin(WeblateModelAdmin):
    list_display = ["name", "code", "direction"]
    search_fields = ["name", "code"]
    list_filter = ("direction",)
    inlines = [PluralAdmin]
    ordering = ["name"]

    def save_related(self, request, form, formsets, change):
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
