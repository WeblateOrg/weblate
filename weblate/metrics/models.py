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
from django.db import models


class Metric(models.Model):
    SCOPE_GLOBAL = 0
    SCOPE_PROJECT = 1
    SCOPE_COMPONENT = 2
    SCOPE_TRANSLATION = 3
    SCOPE_USER = 4

    date = models.DateField(auto_now_add=True)
    scope = models.SmallIntegerField()
    relation = models.IntegerField()
    name = models.CharField(max_length=100)
    value = models.IntegerField(db_index=True)

    class Meta:
        index_together = (("date", "scope", "relation", "name"),)

    def __str__(self):
        return f"<{self.scope}.{self.relation}>:{self.date}:{self.name}={self.value}"
