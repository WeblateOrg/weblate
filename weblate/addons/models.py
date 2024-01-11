# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sentry_sdk
from appconf import AppConf
from django.db import Error as DjangoDatabaseError
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
from weblate.trans.models import Change, Component, Unit
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
    configuration = models.JSONField(default=dict)
    state = models.JSONField(default=dict)
    project_scope = models.BooleanField(default=False, db_index=True)
    repo_scope = models.BooleanField(default=False, db_index=True)

    objects = AddonQuerySet.as_manager()

    class Meta:
        verbose_name = "add-on"
        verbose_name_plural = "add-ons"

    def __str__(self):
        return f"{self.addon.verbose}: {self.component}"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        cls = self.addon_class
        self.project_scope = cls.project_scope
        self.repo_scope = cls.repo_scope

        # Reallocate to repository
        if self.repo_scope and self.component.linked_component:
            self.component = self.component.linked_component

        # Clear add-on cache
        self.component.drop_addons_cache()

        # Store history (if not updating state only)
        if update_fields != ["state"]:
            self.store_change(
                Change.ACTION_ADDON_CREATE
                if self.pk or force_insert
                else Change.ACTION_ADDON_CHANGE
            )

        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self):
        return reverse("addon-detail", kwargs={"pk": self.pk})

    def store_change(self, action):
        self.component.change_set.create(
            action=action,
            user=self.component.acting_user,
            target=self.name,
            details=self.configuration,
        )

    def configure_events(self, events):
        for event in events:
            Event.objects.get_or_create(addon=self, event=event)
        self.event_set.exclude(event__in=events).delete()

    @cached_property
    def addon_class(self):
        return ADDONS[self.name]

    @cached_property
    def addon(self):
        return self.addon_class(self)

    def delete(self, using=None, keep_parents=False):
        # Store history
        self.store_change(Change.ACTION_ADDON_REMOVE)
        # Delete any addon alerts
        if self.addon.alert:
            self.component.delete_alert(self.addon.alert)
        result = super().delete(using=using, keep_parents=keep_parents)
        # Trigger post uninstall action
        self.addon.post_uninstall()
        return result

    def disable(self):
        self.component.log_warning(
            "disabling no longer compatible add-on: %s", self.name
        )
        self.delete()


class Event(models.Model):
    addon = models.ForeignKey(Addon, on_delete=models.deletion.CASCADE, db_index=False)
    event = models.IntegerField(choices=EVENT_CHOICES)

    class Meta:
        unique_together = [("addon", "event")]
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
        "weblate.addons.generate.PrefillAddon",
        "weblate.addons.generate.FillReadOnlyAddon",
        "weblate.addons.json.JSONCustomizeAddon",
        "weblate.addons.xml.XMLCustomizeAddon",
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
    report_error(cause=f"add-on {addon.name} failed", project=component.project)
    # Uninstall no longer compatible add-ons
    if not addon.addon.can_install(component, None):
        addon.disable()


@receiver(vcs_pre_push)
def pre_push(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_PRE_PUSH):
        component.log_debug("running pre_push add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.pre_push", description=addon.name):
                addon.addon.pre_push(component)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed pre_push add-on: %s", addon.name)


@receiver(vcs_post_push)
def post_push(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_POST_PUSH):
        component.log_debug("running post_push add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.post_push", description=addon.name):
                addon.addon.post_push(component)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed post_push add-on: %s", addon.name)


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
        component.log_debug("running post_update add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.post_update", description=addon.name):
                addon.addon.post_update(component, previous_head, skip_push)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed post_update add-on: %s", addon.name)


@receiver(component_post_update)
def component_update(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_COMPONENT_UPDATE):
        component.log_debug("running component_update add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(
                op="addon.component_update", description=addon.name
            ):
                addon.addon.component_update(component)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed component_update add-on: %s", addon.name)


@receiver(vcs_pre_update)
def pre_update(sender, component, **kwargs):
    for addon in Addon.objects.filter_event(component, EVENT_PRE_UPDATE):
        component.log_debug("running pre_update add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.pre_update", description=addon.name):
                addon.addon.pre_update(component)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed pre_update add-on: %s", addon.name)


@receiver(vcs_pre_commit)
def pre_commit(sender, translation, author, **kwargs):
    component = translation.component
    addons = Addon.objects.filter_event(component, EVENT_PRE_COMMIT)
    for addon in addons:
        translation.log_debug("running pre_commit add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.pre_commit", description=addon.name):
                addon.addon.pre_commit(translation, author)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            translation.log_debug("completed pre_commit add-on: %s", addon.name)


@receiver(vcs_post_commit)
def post_commit(sender, component, **kwargs):
    addons = Addon.objects.filter_event(component, EVENT_POST_COMMIT)
    for addon in addons:
        component.log_debug("running post_commit add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.post_commit", description=addon.name):
                addon.addon.post_commit(component)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            component.log_debug("completed post_commit add-on: %s", addon.name)


@receiver(translation_post_add)
def post_add(sender, translation, **kwargs):
    component = translation.component
    addons = Addon.objects.filter_event(component, EVENT_POST_ADD)
    for addon in addons:
        translation.log_debug("running post_add add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(op="addon.post_add", description=addon.name):
                addon.addon.post_add(translation)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            translation.log_debug("completed post_add add-on: %s", addon.name)


@receiver(unit_pre_create)
def unit_pre_create_handler(sender, unit, **kwargs):
    translation = unit.translation
    component = translation.component
    addons = Addon.objects.filter_event(component, EVENT_UNIT_PRE_CREATE)
    for addon in addons:
        translation.log_debug("running unit_pre_create add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(
                op="addon.unit_pre_create", description=addon.name
            ):
                addon.addon.unit_pre_create(unit)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            translation.log_debug("completed unit_pre_create add-on: %s", addon.name)


@receiver(post_save, sender=Unit)
@disable_for_loaddata
def unit_post_save_handler(sender, instance, created, **kwargs):
    translation = instance.translation
    component = translation.component
    addons = Addon.objects.filter_event(component, EVENT_UNIT_POST_SAVE)
    for addon in addons:
        translation.log_debug("running unit_post_save add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(
                op="addon.unit_post_save", description=addon.name
            ):
                addon.addon.unit_post_save(instance, created)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            translation.log_debug("completed unit_post_save add-on: %s", addon.name)


@receiver(store_post_load)
def store_post_load_handler(sender, translation, store, **kwargs):
    component = translation.component
    addons = Addon.objects.filter_event(component, EVENT_STORE_POST_LOAD)
    for addon in addons:
        translation.log_debug("running store_post_load add-on: %s", addon.name)
        try:
            with sentry_sdk.start_span(
                op="addon.store_post_load", description=addon.name
            ):
                addon.addon.store_post_load(translation, store)
        except DjangoDatabaseError:
            raise
        except Exception:
            handle_addon_error(addon, component)
        else:
            translation.log_debug("completed store_post_load add-on: %s", addon.name)
