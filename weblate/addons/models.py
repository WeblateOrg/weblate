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
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.addons.events import (
    EVENT_CHOICES, EVENT_POST_PUSH, EVENT_POST_UPDATE, EVENT_PRE_COMMIT,
    EVENT_POST_COMMIT, EVENT_POST_ADD, EVENT_UNIT_PRE_CREATE,
    EVENT_UNIT_POST_SAVE, EVENT_STORE_POST_LOAD,
)

from weblate.trans.models import Component, Unit
from weblate.trans.signals import (
    vcs_post_push, vcs_post_update, vcs_pre_commit, vcs_post_commit,
    translation_post_add, unit_pre_create, store_post_load,
)
from weblate.utils.classloader import ClassLoader
from weblate.utils.fields import JSONField

# Initialize addons registry
ADDONS = ClassLoader('WEBLATE_ADDONS', False)


class AddonQuerySet(models.QuerySet):
    def filter_component(self, component):
        return self.filter((
            Q(component=component) & Q(project_scope=False)
        ) | (
            Q(component__project=component.project) & Q(project_scope=True)
        ))

    def filter_event(self, component, event):
        if event not in component.addons_cache:
            component.addons_cache[event] = self.filter_component(
                component
            ).filter(
                event__event=event
            )
        return component.addons_cache[event]


@python_2_unicode_compatible
class Addon(models.Model):
    component = models.ForeignKey(
        Component, on_delete=models.deletion.CASCADE
    )
    name = models.CharField(max_length=100)
    configuration = JSONField()
    state = JSONField()
    project_scope = models.BooleanField(default=False, db_index=True)

    objects = AddonQuerySet.as_manager()

    def __str__(self):
        return '{}: {}'.format(self.addon.verbose, self.component)

    def configure_events(self, events):
        for event in events:
            Event.objects.get_or_create(addon=self, event=event)
        self.event_set.exclude(event__in=events).delete()

    @cached_property
    def addon(self):
        return ADDONS[self.name](self)

    def get_absolute_url(self):
        return reverse(
            'addon-detail',
            kwargs={
                'project': self.component.project.slug,
                'component': self.component.slug,
                'pk': self.pk,
            }
        )


@python_2_unicode_compatible
class Event(models.Model):
    addon = models.ForeignKey(Addon, on_delete=models.deletion.CASCADE)
    event = models.IntegerField(choices=EVENT_CHOICES)

    class Meta(object):
        unique_together = ('addon', 'event')

    def __str__(self):
        return '{}: {}'.format(self.addon, self.get_event_display())


class AddonsConf(AppConf):
    ADDONS = (
        'weblate.addons.gettext.GenerateMoAddon',
        'weblate.addons.gettext.UpdateLinguasAddon',
        'weblate.addons.gettext.UpdateConfigureAddon',
        'weblate.addons.gettext.MsgmergeAddon',
        'weblate.addons.gettext.GettextCustomizeAddon',
        'weblate.addons.gettext.GettextAuthorComments',
        'weblate.addons.cleanup.CleanupAddon',
        'weblate.addons.consistency.LangaugeConsistencyAddon',
        'weblate.addons.discovery.DiscoveryAddon',
        'weblate.addons.flags.SourceEditAddon',
        'weblate.addons.flags.TargetEditAddon',
        'weblate.addons.flags.SameEditAddon',
        'weblate.addons.generate.GenerateFileAddon',
        'weblate.addons.json.JSONCustomizeAddon',
        'weblate.addons.properties.PropertiesSortAddon',
    )

    class Meta(object):
        prefix = 'WEBLATE'


@receiver(vcs_post_push)
def post_push(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_POST_PUSH):
        addon.addon.post_push(component)


@receiver(vcs_post_update)
def post_update(sender, component, previous_head, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_POST_UPDATE):
        addon.addon.post_update(component, previous_head)


@receiver(vcs_pre_commit)
def pre_commit(sender, translation, author, **kwargs):
    addons = Addon.objects.filter_event(
        translation.component, EVENT_PRE_COMMIT
    )
    for addon in addons:
        addon.addon.pre_commit(translation, author)


@receiver(vcs_post_commit)
def post_commit(sender, translation, **kwargs):
    addons = Addon.objects.filter_event(
        translation.component, EVENT_POST_COMMIT
    )
    for addon in addons:
        addon.addon.post_commit(translation)


@receiver(translation_post_add)
def post_add(sender, translation, **kwargs):
    addons = Addon.objects.filter_event(
        translation.component, EVENT_POST_ADD
    )
    for addon in addons:
        addon.addon.post_add(translation)


@receiver(unit_pre_create)
def unit_pre_create_handler(sender, unit, **kwargs):
    addons = Addon.objects.filter_event(
        unit.translation.component, EVENT_UNIT_PRE_CREATE
    )
    for addon in addons:
        addon.addon.unit_pre_create(unit)


@receiver(post_save, sender=Unit)
def unit_post_save_handler(sender, instance, created, **kwargs):
    addons = Addon.objects.filter_event(
        instance.translation.component, EVENT_UNIT_POST_SAVE
    )
    for addon in addons:
        addon.addon.unit_post_save(instance, created)


@receiver(store_post_load)
def store_post_load_handler(sender, translation, store, **kwargs):
    addons = Addon.objects.filter_event(
        translation.component, EVENT_STORE_POST_LOAD
    )
    for addon in addons:
        addon.addon.store_post_load(translation, store)
