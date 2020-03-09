# -*- coding: utf-8 -*-
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


from django.conf import settings
from django.db import models


class Memory(models.Model):
    source_language = models.ForeignKey(
        "lang.Language",
        on_delete=models.deletion.CASCADE,
        related_name="memory_source_set",
    )
    target_language = models.ForeignKey(
        "lang.Language",
        on_delete=models.deletion.CASCADE,
        related_name="memory_target_set",
    )
    source = models.TextField()
    target = models.TextField()
    origin = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, null=True, blank=True
    )
    from_file = models.BooleanField()
    shared = models.BooleanField()

    def __str__(self):
        return "Memory: {}:{}".format(self.source_language, self.target_language)
