# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.apps import apps
from django.utils.functional import cached_property
from django.db import models

from weblate.lang.models import Language


class UnitData(models.Model):
    content_hash = models.BigIntegerField()
    project = models.ForeignKey(
        'trans.Project', on_delete=models.deletion.CASCADE
    )
    language = models.ForeignKey(
        Language, null=True, blank=True, on_delete=models.deletion.CASCADE
    )

    class Meta(object):
        abstract = True

    @cached_property
    def units_model(self):
        # Can't cache this property until all the models are loaded.
        apps.check_models_ready()
        return apps.get_model('trans', 'Unit')

    @property
    def related_units(self):
        units = self.units_model.objects.filter(
            content_hash=self.content_hash,
            translation__component__project=self.project,
        )
        if self.language is not None:
            units = units.filter(translation__language=self.language)

        return units.select_related(
            'translation__component__project',
            'translation__language'
        )
