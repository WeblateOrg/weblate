# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from django.db import connection, models
from django.utils.functional import cached_property

from weblate.lang.models import Language

WHERE_HASH = '{0}.content_hash = trans_unit.content_hash'
WHERE_PROJECT = '{0}.project_id = trans_component.project_id'
WHERE_LANGUAGE = '{0}.language_id = trans_translation.language_id'
WHERE_LANGUAGE_WILDCARD = '''
    {0}.language_id = trans_translation.language_id
    OR
    {0}.language_id IS NULL
'''


class UnitData(models.Model):  # noqa: DJ08
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


def filter_query(queryset, table):
    """Filter Unit query to matching UnitData objects.

    Ideally we would use something based on multiple column foreign keys, but
    that is currently not supported by Django and would not handle NULL values
    in a way we need.
    """
    where = [WHERE_HASH.format(table), WHERE_PROJECT.format(table)]
    if table == 'trans_comment':
        where.append(WHERE_LANGUAGE_WILDCARD.format(table))
    else:
        where.append(WHERE_LANGUAGE.format(table))
    if table == 'checks_check':
        if connection.vendor == 'sqlite':
            where.append('checks_check.ignore = 0')
        else:
            where.append('checks_check.ignore = false')
    return queryset.extra(tables=[table], where=where)
