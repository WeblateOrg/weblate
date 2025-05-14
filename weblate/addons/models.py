# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, overload

import sentry_sdk
from appconf import AppConf
from django.db import Error as DjangoDatabaseError
from django.db import models, transaction
from django.db.models import Q, QuerySet
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.functional import cached_property

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Alert, Change, Component, Project, Translation, Unit
from weblate.trans.signals import (
    change_bulk_create,
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

from .base import BaseAddon
from .events import AddonEvent

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from weblate.auth.models import User

# Initialize addons registry
ADDONS = ClassLoader("WEBLATE_ADDONS", construct=False, base_class=BaseAddon)


class AddonQuerySet(models.QuerySet):
    def filter_for_execution(self, component):
        query = (
            Q(component=component)
            | Q(project=component.project)
            | (Q(component__linked_component=component) & Q(repo_scope=True))
            | (Q(component__isnull=True) & Q(project__isnull=True))
        )
        if component.linked_component:
            query |= Q(component=component.linked_component) & Q(repo_scope=True)
        return self.filter(query).prefetch_related("event_set")

    def filter_component(self, component):
        return self.prefetch_related("event_set").filter(component=component)

    def filter_project(self, project):
        return self.prefetch_related("event_set").filter(project=project)

    def filter_sitewide(self):
        return self.prefetch_related("event_set").filter(
            component__isnull=True, project__isnull=True
        )

    def filter_event(self, component, event):
        return component.addons_cache[event]


class Addon(models.Model):
    component = models.ForeignKey(
        Component, on_delete=models.deletion.CASCADE, null=True
    )
    project = models.ForeignKey(Project, on_delete=models.deletion.CASCADE, null=True)
    name = models.CharField(max_length=100)
    configuration = models.JSONField(default=dict)
    state = models.JSONField(default=dict)
    repo_scope = models.BooleanField(default=False, db_index=True)

    objects = AddonQuerySet.as_manager()

    class Meta:
        verbose_name = "add-on"
        verbose_name_plural = "add-ons"

    def __str__(self) -> str:
        return f"{self.addon.verbose}: {self.project or self.component or 'site-wide'}"

    def __init__(self, *args, acting_user: User | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        cls = self.addon_class
        self.repo_scope = cls.repo_scope

        original_component = None
        if cls.project_scope:
            original_component = self.component
            if self.component:
                self.project = self.component.project
            self.component = None

        # Reallocate to repository
        if cls.repo_scope and self.component and self.component.linked_component:
            original_component = self.component
            self.component = self.component.linked_component

        # Store history (if not updating state only)
        if update_fields != ["state"]:
            self.store_change(
                ActionEvents.ADDON_CREATE
                if not self.pk or force_insert
                else ActionEvents.ADDON_CHANGE
            )

        # Clear add-on cache, needs to be after creating Change
        if self.component:
            self.component.drop_addons_cache()
        if original_component:
            original_component.drop_addons_cache()

        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self) -> str:
        return reverse("addon-detail", kwargs={"pk": self.pk})

    def store_change(self, action) -> None:
        Change.objects.create(
            action=action,
            user=self.acting_user,
            project=self.project,
            component=self.component,
            target=self.name,
            details=self.configuration,
        )

    def configure_events(self, events: set[AddonEvent]) -> None:
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
        self.store_change(ActionEvents.ADDON_REMOVE)
        # Delete any addon alerts
        if self.addon.alert:
            if self.component:
                self.component.delete_alert(self.addon.alert)
            elif self.project:
                Alert.objects.filter(
                    component__project=self.project,
                    name=self.addon.alert,
                ).delete()
            else:
                Alert.objects.filter(name=self.addon.alert).delete()

        result = super().delete(using=using, keep_parents=keep_parents)
        if self.component:
            self.component.drop_addons_cache()
        # Trigger post uninstall action
        self.addon.post_uninstall()
        return result

    def disable(self) -> None:
        self.log_warning("disabling no longer compatible add-on: %s", self.name)
        self.delete()

    @cached_property
    def logger(self) -> logging.Logger:
        return logging.getLogger("weblate.addons")

    def log_warning(self, message: str, *args) -> None:
        if self.project:
            self.project.log_warning(message, *args)
        elif self.component:
            self.component.log_warning(message, *args)
        else:
            self.logger.warning(message, *args)

    def log_debug(self, message: str, *args) -> None:
        if self.project:
            self.project.log_debug(message, *args)
        elif self.component:
            self.component.log_debug(message, *args)
        else:
            self.logger.debug(message, *args)

    def get_addon_activity_logs(self) -> QuerySet[AddonActivityLog]:
        """Return activity logs for add-on."""
        return self.addonactivitylog_set.order_by("-created")


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
        "weblate.addons.consistency.LanguageConsistencyAddon",
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
        "weblate.addons.webhooks.WebhookAddon",
    )

    LOCALIZE_CDN_URL = None
    LOCALIZE_CDN_PATH = None

    # How long to keep add-on activity log entries
    ADDON_ACTIVITY_LOG_EXPIRY = 180

    class Meta:
        prefix = ""


# Events to exclude from logging
NO_LOG_EVENTS = {
    AddonEvent.EVENT_UNIT_PRE_CREATE,
    AddonEvent.EVENT_UNIT_POST_SAVE,
    AddonEvent.EVENT_STORE_POST_LOAD,
}

# Repository scoped events
REPO_EVENTS = {
    AddonEvent.EVENT_PRE_UPDATE,
    AddonEvent.EVENT_POST_UPDATE,
    AddonEvent.EVENT_PRE_PUSH,
    AddonEvent.EVENT_POST_PUSH,
    AddonEvent.EVENT_COMPONENT_UPDATE,
}


def execute_addon_event(
    addon: Addon,
    component: Component,
    scope: Translation | Component,
    event: AddonEvent,
    method: str | Callable[[Addon, Component], None],
    args: tuple | None = None,
) -> None:
    # Trigger repository scoped add-ons only on the main component
    if addon.repo_scope and component.linked_component and event in REPO_EVENTS:
        return

    # Log logging result and error flag for add-on activity log
    log_result = None
    error_occurred = False

    with transaction.atomic():
        scope.log_debug("running %s add-on: %s", event.label, addon.name)
        # Skip unsupported components silently
        if not addon.component and not addon.addon.can_install(component, None):
            scope.log_debug(
                "Skipping incompatible %s add-on: %s for component: %s",
                event.label,
                addon.name,
                component.name,
            )
            return

        try:
            # Execute event in senty span to track performance
            with sentry_sdk.start_span(op=f"addon.{event.name}", name=addon.name):
                if isinstance(method, str):
                    log_result = getattr(addon.addon, method)(*args)
                else:
                    # Callback is used in tasks
                    log_result = method(addon, component)
        except DjangoDatabaseError:
            raise
        except Exception as error:
            # Log failure
            error_occurred = True
            log_result = str(error)
            scope.log_error("failed %s add-on: %s: %s", event.label, addon.name, error)
            report_error(f"add-on {addon.name} failed", project=component.project)
            # Uninstall no longer compatible add-ons
            if not addon.addon.can_install(component, None):
                addon.disable()
                component.drop_addons_cache()
        else:
            scope.log_debug("completed %s add-on: %s", event.label, addon.name)
        finally:
            # Check if add-on is still installed and log activity
            if event not in NO_LOG_EVENTS and addon.pk is not None:
                AddonActivityLog.objects.create(
                    addon=addon,
                    component=component,
                    event=event,
                    details={"result": log_result, "error": error_occurred},
                )


@overload
def handle_addon_event(
    event: AddonEvent,
    method: str,
    args: tuple,
    *,
    component: Component,
    translation: None = None,
    addon_queryset: AddonQuerySet | None = None,
    auto_scope: bool = False,
) -> None: ...


@overload
def handle_addon_event(
    event: AddonEvent,
    method: str,
    args: tuple,
    *,
    component: None = None,
    translation: Translation,
    addon_queryset: AddonQuerySet | None = None,
    auto_scope: bool = False,
) -> None: ...


@overload
def handle_addon_event(
    event: AddonEvent,
    method: Callable[[Addon, Component], None],
    args: None = None,
    *,
    component: None = None,
    translation: None = None,
    addon_queryset: AddonQuerySet | None,
    auto_scope: bool,
) -> None: ...


@transaction.atomic
def handle_addon_event(
    event,
    method,
    args=None,
    *,
    component=None,
    translation=None,
    addon_queryset=None,
    auto_scope=False,
) -> None:
    # Scope is used for logging
    scope = translation or component

    # Shortcuts for frequently used variables
    if component is None and translation is not None:
        component = translation.component

    if component is None and not auto_scope:
        msg = "Missing event scope!"
        raise ValueError(msg)

    # EVENT_DAILY uses custom queryset because it is not triggered from the
    # object scope
    if addon_queryset is None:
        addon_queryset = Addon.objects.filter_event(component, event)

    for addon in addon_queryset:
        if scope is not None:
            execute_addon_event(addon, component, scope, event, method, args)
        else:
            components: Iterable[Component]
            if addon.component:
                components = [addon.component]
            elif addon.project:
                components = addon.project.component_set.iterator()
            else:
                components = Component.objects.iterator()

            for scope_component in components:
                execute_addon_event(
                    addon, scope_component, scope_component, event, method, args
                )


@receiver(vcs_pre_push)
def pre_push(sender, component: Component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_PUSH,
        "pre_push",
        (component,),
        component=component,
    )


@receiver(vcs_post_push)
def post_push(sender, component: Component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_PUSH,
        "post_push",
        (component,),
        component=component,
    )


@receiver(vcs_post_update)
def post_update(
    sender,
    component: Component,
    previous_head: str,
    skip_push: bool = False,
    **kwargs,
) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_UPDATE,
        "post_update",
        (component, previous_head, skip_push),
        component=component,
    )


@receiver(component_post_update)
def component_update(sender, component: Component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_COMPONENT_UPDATE,
        "component_update",
        (component,),
        component=component,
    )


@receiver(vcs_pre_update)
def pre_update(sender, component: Component, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_UPDATE,
        "pre_update",
        (component,),
        component=component,
    )


@receiver(vcs_pre_commit)
def pre_commit(
    sender, translation: Translation, author: str, store_hash: bool, **kwargs
) -> None:
    handle_addon_event(
        AddonEvent.EVENT_PRE_COMMIT,
        "pre_commit",
        (translation, author, store_hash),
        translation=translation,
    )


@receiver(vcs_post_commit)
def post_commit(sender, component: Component, store_hash: bool, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_COMMIT,
        "post_commit",
        (component, store_hash),
        component=component,
    )


@receiver(translation_post_add)
def post_add(sender, translation: Translation, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_POST_ADD,
        "post_add",
        (translation,),
        translation=translation,
    )


@receiver(unit_pre_create)
def unit_pre_create_handler(sender, unit: Unit, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_UNIT_PRE_CREATE,
        "unit_pre_create",
        (unit,),
        translation=unit.translation,
    )


@receiver(post_save, sender=Unit)
@disable_for_loaddata
def unit_post_save_handler(sender, instance: Unit, created, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_UNIT_POST_SAVE,
        "unit_post_save",
        (instance, created),
        translation=instance.translation,
    )


@receiver(store_post_load)
def store_post_load_handler(sender, translation: Translation, store, **kwargs) -> None:
    handle_addon_event(
        AddonEvent.EVENT_STORE_POST_LOAD,
        "store_post_load",
        (translation, store),
        translation=translation,
    )


@receiver(post_save, sender=Change)
@disable_for_loaddata
def change_post_save_handler(sender, instance: Change, created, **kwargs) -> None:
    """Handle Change post save signal."""
    if created:  # ignore Change updates, they should not be updated anyway
        bulk_change_create_handler(sender, [instance])


@receiver(change_bulk_create)
@disable_for_loaddata
def bulk_change_create_handler(sender, instances: list[Change], **kwargs) -> None:
    """Handle Change bulk create signal."""
    from weblate.addons.tasks import addon_change

    # Filter out events that have a subscriber
    # It currently also includes all project and site-wide events as there is currently
    # no effective way to filter and these are not that frequent.
    filtered = [
        change.pk
        for change in instances
        if change.component is None
        or AddonEvent.EVENT_CHANGE in change.component.addons_cache
    ]

    if filtered:
        addon_change.delay_on_commit(filtered)


class AddonActivityLog(models.Model):
    addon = models.ForeignKey(Addon, on_delete=models.deletion.CASCADE)
    component = models.ForeignKey(Component, on_delete=models.deletion.CASCADE)
    event = models.IntegerField(choices=AddonEvent.choices)
    created = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    class Meta:
        verbose_name = "add-on activity log"
        verbose_name_plural = "add-on activity logs"
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.addon}: {self.get_event_display()} at {self.created}"
