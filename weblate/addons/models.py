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

from appconf import AppConf

from django.db import models

from weblate.addons.events import EVENT_CHOICES
from weblate.trans.models import SubProject
from weblate.utils.fields import JSONField


class Addon(models.Model):
    component = models.ForeignKey(SubProject)
    name = models.CharField(max_length=100)
    configuration = JSONField()
    state = JSONField()

    class Meta(object):
        unique_together = ('component', 'name')

    def configure_events(self, events):
        for event in events:
            Event.objects.get_or_create(addon=self, event=event)
        self.event_set.exclude(event__in=events).delete()


class Event(models.Model):
    addon = models.ForeignKey(Addon)
    event = models.IntegerField(choices=EVENT_CHOICES)

     class Meta(object):
        unique_together = ('addon', 'event')


class AddonsConf(AppConf):
    ADDONS = (
        'weblate.addons.gettext.GenerateMoAddon',
    )

    class Meta(object):
        prefix = 'WEBLATE'
