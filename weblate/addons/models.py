# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

import sentry_sdk
from appconf import AppConf
from django.db import Error as DjangoDatabaseError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.functional import cached_property

from weblate.addons.events import AddonEvent
from weblate.trans.models import Change, Component, Translation, Unit
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

if TYPE_CHECKING:
    from collections.abc import Callable

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

    def __str__(self) -> str:
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

    def store_change(self, action) -> None:
        self.component.change_set.create(
            action=action,
            user=self.component.acting_user,
            target=self.name,
            details=self.configuration,
        )

    def configure_events(self, events) -> None:
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

    def disable(self) -> None:
        self.component.log_warning(
            "disabling no longer compatible add-on: %s", self.name
        )
        self.delete()


class Event(models.Model):
    addon = models.ForeignKey(Addon, on_delete=models.deletion.CASCADE, db_index=False)
    event = models.IntegerField(choices=AddonEvent.choices)

    class Meta:
        unique_together = [("addon", "event")]
        verbose_name = "add-on event"
        verbose_name_plural = "add-on events"

    def __str__(self) -> str:
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


def handle_addon_event(
    event: AddonEvent,
    method: str | Callable,
    args: tuple | None = None,
    *,
    component: Component | None = None,
    translation: Translation | None = None,
    addon_queryset: AddonQuerySet | None = None,
    auto_scope: bool = False,
) -> None:
    # Scope is used for logging
    scope = translation or component

    # Shortcuts for frequently used variables
    if component is None and translation is not None:
        component = translation.component

    # EVENT_DAILY uses custom queryset because it is not triggered from the
    # object scope
    if addon_queryset is None:
        addon_queryset = Addon.objects.filter_event(component, event)

    # Filter matching events
    for addon in addon_queryset:
        with transaction.atomic():
            # Extract scope from the add-on model, used for EVENT_DAILY
            if auto_scope:
                component = scope = addon.component

            scope.log_debug("running %s add-on: %s", event.label, addon.name)
            try:
                # Execute event in senty span to track performance
                with sentry_sdk.start_span(
                    op=f"addon.{event.name}", description=addon.name
                ):
                    if isinstance(method, str):
                        getattr(addon.addon, method)(*args)
                    else:
                        # Callback is used in tasks
                        method(addon)
            except DjangoDatabaseError:
                raise
            except Exception as error:
                # Log failure
                scope.log_error(
                    "failed %s add-on: %s: %s", event.label, addon.name, error
                )
                report_error(
                    cause=f"add-on {addon.name} failed", project=component.project
                )
                # Uninstall no longer compatible add-ons
                if not addon.addon.can_install(component, None):
                    scope.log_warning(
                        "uninstalling incompatible %s add-on: %s",
                        event.label,
                        addon.name,
                    )
                    addon.disable()
            else:
                scope.log_debug("completed %s add-on: %s", event.label, addon.name)


@receiver(vcs_pre_push)
def pre_push(sender, component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_PUSH,
        "pre_push",
        (component,),
        component=component,
    )


@receiver(vcs_post_push)
def post_push(sender, component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_PUSH,
        "post_push",
        (component,),
        component=component,
    )


@receiver(vcs_post_update)
def post_update(
    sender,
    component,
    previous_head: str,
    child: bool = False,
    skip_push: bool = False,
    **kwargs,
) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_UPDATE,
        "post_update",
        (component, previous_head, skip_push, child),
        component=component,
    )


@receiver(component_post_update)
def component_update(sender, component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_COMPONENT_UPDATE,
        "component_update",
        (component,),
        component=component,
    )


@receiver(vcs_pre_update)
def pre_update(sender, component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_UPDATE,
        "pre_update",
        (component,),
        component=component,
    )


@receiver(vcs_pre_commit)
def pre_commit(sender, translation, author, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_COMMIT,
        "pre_commit",
        (translation, author),
        translation=translation,
    )


@receiver(vcs_post_commit)
def post_commit(sender, component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_COMMIT,
        "post_commit",
        (component,),
        component=component,
    )


@receiver(translation_post_add)
def post_add(sender, translation, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_ADD,
        "post_add",
        (translation,),
        translation=translation,
    )


@receiver(unit_pre_create)
def unit_pre_create_handler(sender, unit, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_UNIT_PRE_CREATE,
        "unit_pre_create",
        (unit,),
        translation=unit.translation,
    )


@receiver(post_save, sender=Unit)
@disable_for_loaddata
def unit_post_save_handler(sender, instance, created, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_UNIT_POST_SAVE,
        "unit_post_save",
        (instance, created),
        translation=instance.translation,
    )


@receiver(store_post_load)
def store_post_load_handler(sender, translation, store, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_STORE_POST_LOAD,
        "store_post_load",
        (translation, store),
        translation=translation,
    )
