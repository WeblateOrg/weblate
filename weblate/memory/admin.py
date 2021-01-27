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
