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

from django.contrib.admin import ModelAdmin
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible


class WeblateModelAdmin(ModelAdmin):
    """Customized Model Admin object."""

    delete_confirmation_template = \
        'wladmin/delete_confirmation.html'
    delete_selected_confirmation_template = \
        'wladmin/delete_selected_confirmation.html'


class ConfigurationErrorManager(models.Manager):
    def add(self, name, message, timestamp=None):
        if timestamp is None:
            timestamp = timezone.now()
        obj, created = self.get_or_create(
            name=name,
            defaults={
                'message': message,
                'timestamp': timestamp,
            }
        )
        if created:
            return obj
        if obj.message != message or obj.timestamp != timestamp:
            obj.message = message
            obj.timestamp = timestamp
            obj.save(update_fields=['message', 'timestamp'])
        return obj

    def remove(self, name):
        self.filter(name=name).delete()


@python_2_unicode_compatible
class ConfigurationError(models.Model):
    name = models.CharField(unique=True, max_length=150)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    ignored = models.BooleanField(default=False)

    objects = ConfigurationErrorManager()

    class Meta(object):
        ordering = ['-timestamp']
        index_together = [
            ('ignored', 'timestamp'),
        ]

    def __str__(self):
        return self.name
