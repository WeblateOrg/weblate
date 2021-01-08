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
from typing import Dict

from django.db import models


class SettingQuerySet(models.QuerySet):
    def get_settings_dict(self, category: int) -> Dict:
        return dict(self.filter(category=category).values_list("name", "value"))


class Setting(models.Model):
    CATEGORY_UI = 1

    category = models.IntegerField(
        choices=((CATEGORY_UI, "UI"),),
        db_index=True,
    )
    name = models.CharField(max_length=100)
    value = models.JSONField()

    objects = SettingQuerySet.as_manager()

    class Meta:
        unique_together = ("category", "name")

    def __str__(self):
        return f"{self.name}:{self.value}"
