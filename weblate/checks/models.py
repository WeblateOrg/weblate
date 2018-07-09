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

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.checks import CHECKS
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.unitdata import UnitData


@python_2_unicode_compatible
class Check(UnitData):
    check = models.CharField(max_length=50, choices=CHECKS.get_choices())
    ignore = models.BooleanField(db_index=True, default=False)

    _for_unit = None

    @property
    def for_unit(self):
        return self._for_unit

    @cached_property
    def check_obj(self):
        try:
            return CHECKS[self.check]
        except KeyError:
            return None

    @for_unit.setter
    def for_unit(self, value):
        self._for_unit = value

    class Meta(object):
        unique_together = ('content_hash', 'project', 'language', 'check')
        index_together = [
            ('project', 'language', 'content_hash'),
        ]

    def __str__(self):
        return '{0}/{1}: {2}'.format(
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        if self.check_obj:
            return self.check_obj.description
        return self.check

    def get_severity(self):
        if self.check_obj:
            return self.check_obj.severity
        return 'info'

    def get_doc_url(self):
        if self.check_obj:
            return self.check_obj.get_doc_url()
        return ''

    def set_ignore(self):
        """Set ignore flag."""
        self.ignore = True
        self.save()


@receiver(post_save, sender=Check)
@disable_for_loaddata
def update_failed_check_flag(sender, instance, **kwargs):
    """Update related unit failed check flag."""
    if instance.language is None:
        return
    related = instance.related_units
    if instance.for_unit is not None:
        related = related.exclude(pk=instance.for_unit)
    for unit in related:
        unit.update_has_failing_check(False)
        unit.translation.invalidate_cache()
