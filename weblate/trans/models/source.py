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
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.trans.validators import validate_check_flags
from weblate.trans.util import PRIORITY_CHOICES


@python_2_unicode_compatible
class Source(models.Model):
    id_hash = models.BigIntegerField()
    component = models.ForeignKey(
        'Component', on_delete=models.deletion.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    priority = models.IntegerField(
        default=100,
        choices=PRIORITY_CHOICES,
    )
    check_flags = models.TextField(
        default='',
        validators=[validate_check_flags],
        blank=True,
    )
    context = models.TextField(default='', blank=True)

    class Meta(object):
        app_label = 'trans'
        unique_together = ('id_hash', 'component')
        ordering = ('id', )

    @cached_property
    def units_model(self):
        # Can't cache this property until all the models are loaded.
        apps.check_models_ready()
        return apps.get_model('trans', 'Unit')

    def __init__(self, *args, **kwargs):
        super(Source, self).__init__(*args, **kwargs)
        self.priority_modified = False
        self.check_flags_modified = False

    def __str__(self):
        return 'src:{0}'.format(self.id_hash)

    def save(self, force_insert=False, **kwargs):
        """
        Wrapper around save to indicate whether priority has been
        modified.
        """
        if force_insert:
            self.priority_modified = (self.priority != 100)
            self.check_flags_modified = (self.check_flags != '')
        else:
            old = Source.objects.get(pk=self.pk)
            self.priority_modified = (old.priority != self.priority)
            self.check_flags_modified = (old.check_flags != self.check_flags)
        super(Source, self).save(force_insert, **kwargs)

    @property
    def unit(self):
        try:
            translation = self.component.translation_set.all()[0]
        except IndexError:
            return None
        try:
            return translation.unit_set.get(id_hash=self.id_hash)
        except ObjectDoesNotExist:
            return None

    def units(self):
        return self.units_model.objects.filter(
            id_hash=self.id_hash,
            translation__component=self.component
        )

    def get_absolute_url(self):
        return reverse('review_source', kwargs={
            'project': self.component.project.slug,
            'component': self.component.slug,
        })
