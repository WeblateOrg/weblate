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

import dateutil.parser
import requests
from django.conf import settings
from django.contrib.admin import ModelAdmin
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy

from weblate import USER_AGENT
from weblate.auth.models import User
from weblate.trans.models import Component, Project
from weblate.utils.site import get_site_url
from weblate.utils.stats import GlobalStats


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
    ignored = models.BooleanField(default=False, db_index=True)

    objects = ConfigurationErrorManager()

    class Meta(object):
        index_together = [
            ('ignored', 'timestamp'),
        ]

    def __str__(self):
        return self.name


SUPPORT_NAMES = {
    'community': ugettext_lazy('Community support'),
    'hosted': ugettext_lazy('Hosted service'),
    'basic': ugettext_lazy('Basic self-hosted support'),
    'extended': ugettext_lazy('Extended self-hosted support'),
}


class SupportStatusManager(models.Manager):
    def get_current(self):
        try:
            return self.latest('expiry')
        except SupportStatus.DoesNotExist:
            return SupportStatus(name='community')


@python_2_unicode_compatible
class SupportStatus(models.Model):
    name = models.CharField(max_length=150)
    secret = models.CharField(max_length=400)
    expiry = models.DateTimeField(db_index=True, null=True)

    objects = SupportStatusManager()

    def get_verbose(self):
        return SUPPORT_NAMES.get(self.name, self.name)

    def __str__(self):
        return '{}:{}'.format(self.name, self.expiry)

    def refresh(self):
        stats = GlobalStats()
        data = {
            'secret': self.secret,
            'site_url': get_site_url(),
            'users': User.objects.count(),
            'projects': Project.objects.count(),
            'components': Component.objects.count(),
            'languages': stats.languages,
        }
        headers = {
            'User-Agent': USER_AGENT,
        }
        response = requests.request(
            'post', settings.SUPPORT_API_URL, headers=headers, data=data
        )
        response.raise_for_status()
        payload = response.json()
        self.name = payload['name']
        self.expiry = dateutil.parser.parse(payload['expiry'])
