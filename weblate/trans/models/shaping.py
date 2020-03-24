#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from weblate.trans.fields import RegexField


class Shaping(models.Model):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    shaping_regex = RegexField(max_length=190)
    key = models.CharField(max_length=190, db_index=True)

    class Meta:
        unique_together = (("key", "component", "shaping_regex"),)

    def __str__(self):
        return "{}: {}".format(self.component, self.key)
