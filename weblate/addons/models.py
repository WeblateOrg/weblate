#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from appconf import AppConf
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.functional import cached_property

from weblate.addons.events import (
    EVENT_CHOICES,
    EVENT_COMPONENT_UPDATE,
    EVENT_POST_ADD,
    EVENT_POST_COMMIT,
    EVENT_POST_PUSH,
    EVENT_POST_UPDATE,
    EVENT_PRE_COMMIT,
    EVENT_PRE_PUSH,
    EVENT_PRE_UPDATE,
    EVENT_STORE_POST_LOAD,
    EVENT_UNIT_POST_SAVE,
    EVENT_UNIT_PRE_CREATE,
)
from weblate.trans.models import Component, Unit
from weblate.trans.signals import (
    component_post_update,
    store_post_load,
    translation_post_add,
    unit_pre_create,
    vcs_post_commit,
    vcs_post_push,
    vcs_post_update,
    vcs_pre_commit,
    vcs_pre_push,
    vcs_pre_update,
)
from weblate.utils.classloader import ClassLoader
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.errors import report_error
from weblate.utils.fields import JSONField

# Initialize addons registry
ADDONS = ClassLoader("WEBLATE_ADDONS", False)


class AddonQuerySet(models.QuerySet):
    def filter_component(self, component):
        return self.prefetch_related("event_set").filter(
            (Q(component=component) & Q(project_scope=False))
            | (Q(component__project=component.project) & Q(project_scope=True))
            | (Q(component__linked_component=component) & Q(repo_scope=True))
            | (Q(component=component.linked_component) & Q(repo_scope=True))
        )

    def filter_event(self, component, event):
        return component.addons_cache[event]


class Addon(models.Model):
    component = models.ForeignKey(Component, on_delete=models.deletion.CASCADE)
    name = models.CharField(max_length=100)
    configuration = JSONField()
    state = JSONField()
    project_scope = models.BooleanField(default=False, db_index=True)
    repo_scope = models.BooleanField(default=False, db_index=True)

    objects = AddonQuerySet.as_manager()

    class Meta:
        verbose_name = "add-on"
        verbose_name_plural = "add-ons"

    def __str__(self):
        return f"{self.addon.verbose}: {self.component}"

    def get_absolute_url(self):
        return reverse(
            "addon-detail",
            kwargs={
                "project": self.component.project.slug,
                "component": self.component.slug,
                "pk": self.pk,
            },
        )

    def configure_events(self, events):
        for event in events:
            Event.objects.get_or_create(addon=self, event=event)
        self.event_set.exclude(event__in=events).delete()

    @cached_property
    def addon(self):
        return ADDONS[self.name](self)

    def delete(self, *args, **kwargs):
        # Delete any addon alerts
        if self.addon.alert:
            self.component.delete_alert(self.addon.alert)
        super().delete(*args, **kwargs)


class Event(models.Model):
    addon = models.ForeignKey(Addon, on_delete=models.deletion.CASCADE)
    event = models.IntegerField(choices=EVENT_CHOICES)

    class Meta:
        unique_together = ("addon", "event")
        verbose_name = "add-on event"
        verbose_name_plural = "add-on events"

    def __str__(self):
        return f"{self.addon}: {self.get_event_display()}"


class AddonsConf(AppConf):
    WEBLATE_ADDONS = (
        "weblate.addons.gettext.GenerateMoAddon",
        "weblate.addons.gettext.UpdateLinguasAddon",
        "weblate.addons.gettext.UpdateConfigureAddon",
        "weblate.addons.gettext.MsgmergeAddon",
        "weblate.addons.gettext.GettextCustomizeAddon",
        "weblate.addons.gettext.GettextAuthorComments",
        "weblate.addons.cleanup.CleanupAddon",
        "weblate.addons.cleanup.RemoveBlankAddon",
        "weblate.addons.consistency.LangaugeConsistencyAddon",
        "weblate.addons.discovery.DiscoveryAddon",
        "weblate.addons.autotranslate.AutoTranslateAddon",
        "weblate.addons.flags.SourceEditAddon",
        "weblate.addons.flags.TargetEditAddon",
        "weblate.addons.flags.SameEditAddon",
        "weblate.addons.flags.BulkEditAddon",
        "weblate.addons.generate.GenerateFileAddon",
        "weblate.addons.generate.PseudolocaleAddon",
        "weblate.addons.json.JSONCustomizeAddon",
        "weblate.addons.properties.PropertiesSortAddon",
        "weblate.addons.git.GitSquashAddon",
        "weblate.addons.removal.RemoveComments",
        "weblate.addons.removal.RemoveSuggestions",
        "weblate.addons.resx.ResxUpdateAddon",
        "weblate.addons.yaml.YAMLCustomizeAddon",
        "weblate.addons.cdn.CDNJSAddon",
    )

    LOCALIZE_CDN_URL = None
    LOCALIZE_CDN_PATH = None

    class Meta:
        prefix = ""


def handle_addon_error(addon, component):
    report_error(cause="addon error")
    # Uninstall no longer compatible addons
    if not addon.addon.can_install(component, None):
        component.log_warning("disabling no longer compatible addon: %s", addon.name)
        addon.delete()


@receiver(vcs_pre_push)
def pre_push(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_PRE_PUSH):
        component.log_debug("running pre_push addon: %s", addon.name)
        try:
            addon.addon.pre_push(component)
        except Exception:
            handle_addon_error(addon, component)


@receiver(vcs_post_push)
def post_push(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_POST_PUSH):
        component.log_debug("running post_push addon: %s", addon.name)
        try:
            addon.addon.post_push(component)
        except Exception:
            handle_addon_error(addon, component)


@receiver(vcs_post_update)
def post_update(
    sender,
    component,
    previous_head: str,
    child: bool = False,
    skip_push: bool = False,
    **kwargs,
):
    for addon in Addon.objects.filter_event(component, EVENT_POST_UPDATE):
        if child and addon.repo_scope:
            continue
        component.log_debug("running post_update addon: %s", addon.name)
        try:
            addon.addon.post_update(component, previous_head, skip_push)
        except Exception:
            handle_addon_error(addon, component)


@receiver(component_post_update)
def component_update(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_COMPONENT_UPDATE):
        component.log_debug("running component_update addon: %s", addon.name)
        try:
            addon.addon.component_update(component)
        except Exception:
            handle_addon_error(addon, component)


@receiver(vcs_pre_update)
def pre_update(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_PRE_UPDATE):
        component.log_debug("running pre_update addon: %s", addon.name)
        try:
            addon.addon.pre_update(component)
        except Exception:
            handle_addon_error(addon, component)


@receiver(vcs_pre_commit)
def pre_commit(sender, translation, author, **kwargs):
    addons = Addon.objects.filter_event(translation.component, EVENT_PRE_COMMIT)
    for addon in addons:
        translation.log_debug("running pre_commit addon: %s", addon.name)
        try:
            addon.addon.pre_commit(translation, author)
        except Exception:
            handle_addon_error(addon, translation.component)


@receiver(vcs_post_commit)
def post_commit(sender, component, **kwargs):
    addons = Addon.objects.filter_event(component, EVENT_POST_COMMIT)
    for addon in addons:
        component.log_debug("running post_commit addon: %s", addon.name)
        try:
            addon.addon.post_commit(component)
        except Exception:
            handle_addon_error(addon, component)


@receiver(translation_post_add)
def post_add(sender, translation, **kwargs):
    addons = Addon.objects.filter_event(translation.component, EVENT_POST_ADD)
    for addon in addons:
        translation.log_debug("running post_add addon: %s", addon.name)
        try:
            addon.addon.post_add(translation)
        except Exception:
            handle_addon_error(addon, translation.component)


@receiver(unit_pre_create)
def unit_pre_create_handler(sender, unit, **kwargs):
    addons = Addon.objects.filter_event(
        unit.translation.component, EVENT_UNIT_PRE_CREATE
    )
    for addon in addons:
        unit.translation.log_debug("running unit_pre_create addon: %s", addon.name)
        try:
            addon.addon.unit_pre_create(unit)
        except Exception:
            handle_addon_error(addon, unit.translation.component)


@receiver(post_save, sender=Unit)
@disable_for_loaddata
def unit_post_save_handler(sender, instance, created, **kwargs):
    addons = Addon.objects.filter_event(
        instance.translation.component, EVENT_UNIT_POST_SAVE
    )
    for addon in addons:
        instance.translation.log_debug("running unit_post_save addon: %s", addon.name)
        try:
            addon.addon.unit_post_save(instance, created)
        except Exception:
            handle_addon_error(addon, instance.translation.component)


@receiver(store_post_load)
def store_post_load_handler(sender, translation, store, **kwargs):
    addons = Addon.objects.filter_event(translation.component, EVENT_STORE_POST_LOAD)
    for addon in addons:
        translation.log_debug("running store_post_load addon: %s", addon.name)
        try:
            addon.addon.store_post_load(translation, store)
        except Exception:
            handle_addon_error(addon, translation.component)
