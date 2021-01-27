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

from weblate.trans.fields import RegexField


class Variant(models.Model):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    variant_regex = RegexField(max_length=190, blank=True)
    # This really should be a TextField, but it does not work with unique
    # index and MySQL
    key = models.CharField(max_length=768)
    defining_units = models.ManyToManyField("Unit", related_name="defined_variants")

    class Meta:
        unique_together = (("key", "component", "variant_regex"),)
        verbose_name = "variant definition"
        verbose_name_plural = "variant definitions"

    def __str__(self):
        return f"{self.component}: {self.key}"
