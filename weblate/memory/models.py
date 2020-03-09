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


from functools import reduce

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext


class MemoryQuerySet(models.QuerySet):
    def filter_type(self, user=None, project=None, use_shared=False, use_file=False):
        query = []
        if use_file:
            query.append(models.Q(from_file=use_file))
        if use_shared:
            query.append(models.Q(shared=use_shared))
        if project:
            query.append(models.Q(project=project))
        if user:
            query.append(models.Q(user=user))
        return self.filter(reduce(lambda x, y: x | y, query))

    def lookup(self, source_language, target_language, text, user, project, use_shared):
        # Type filtering
        result = self.filter_type(
            user=user, project=project, use_shared=use_shared, use_file=True
        )
        # Language filtering
        result = result.filter(
            source_language=source_language, target_language=target_language
        )
        # Full-text search on source
        return result.filter(source__search=text)


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
    from_file = models.BooleanField(db_index=True)
    shared = models.BooleanField(db_index=True)

    objects = MemoryQuerySet.as_manager()

    def __str__(self):
        return "Memory: {}:{}".format(self.source_language, self.target_language)

    def get_origin_display(self):
        if self.project:
            text = pgettext("Translation memory category", "Project: {}")
        elif self.user:
            text = pgettext("Translation memory category", "Personal: {}")
        elif self.shared:
            text = pgettext("Translation memory category", "Shared: {}")
        elif self.from_file:
            text = pgettext("Translation memory category", "File: {}")
        else:
            text = "Unknown: {}"
        return text.format(self.origin)
