# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.db import models
from django.utils.encoding import python_2_unicode_compatible

from weblate.lang.models import Language


@python_2_unicode_compatible
class Memory(models.Model):
    source_language = models.ForeignKey(
        Language,
        related_name='memory_source',
    )
    target_language = models.ForeignKey(
        Language,
        related_name='memory_target',
    )
    source = models.TextField()
    target = models.TextField()
    origin = models.TextField()

    class Meta(object):
        ordering = ['source']
        index_together = [
            ('source_language', 'source'),
        ]
        unique_together = [
            (
                'source_language', 'target_language',
                'source', 'target',
                'origin',
            ),
        ]

    def __str__(self):
        return '{} ({}): {} ({})'.format(
            self.source,
            self.source_language,
            self.target,
            self.target_language,
        )
