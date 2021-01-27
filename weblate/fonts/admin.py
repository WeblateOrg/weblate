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

from weblate.fonts.models import FontOverride
from weblate.wladmin.models import WeblateModelAdmin


class FontAdmin(WeblateModelAdmin):
    list_display = ["family", "style", "project", "user"]
    search_fields = ["family", "style"]
    list_filter = [("project", admin.RelatedOnlyFieldListFilter)]
    ordering = ["family", "style"]


class InlineFontOverrideAdmin(admin.TabularInline):
    model = FontOverride
    extra = 0


class FontGroupAdmin(WeblateModelAdmin):
    list_display = ["name", "font", "project"]
    search_fields = ["name", "font__family"]
    list_filter = [("project", admin.RelatedOnlyFieldListFilter)]
    ordering = ["name"]
    inlines = [InlineFontOverrideAdmin]
