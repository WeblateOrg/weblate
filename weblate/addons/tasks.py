# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from datetime import timedelta

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpRequest
from django.utils import timezone
from django.utils.timezone import now
from lxml import html

from weblate.addons.events import AddonEvent
from weblate.addons.models import Addon, AddonActivityLog, handle_addon_event
from weblate.lang.models import Language
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import Change, Component, Project
from weblate.utils.celery import app
from weblate.utils.hash import calculate_checksum
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.requests import request

IGNORED_TAGS = {"script", "style"}


@app.task(trail=False)
def cdn_parse_html(addon_id: int, component_id: int) -> None:
    try:
        addon = Addon.objects.get(pk=addon_id)
    except Addon.DoesNotExist:
        return

    component = Component.objects.get(pk=component_id)
    source_translation = component.source_translation
    source_units = set(source_translation.unit_set.values_list("source", flat=True))
    units = []
    errors = []

    for filename in addon.configuration["files"].splitlines():
        filename = filename.strip()
        try:
            if filename.startswith(("http://", "https://")):
                with request("get", filename) as handle:
                    content = handle.text
            else:
                with open(os.path.join(component.full_path, filename)) as handle:
                    content = handle.read()
        except OSError as error:
            errors.append({"filename": filename, "error": str(error)})
            continue

        document = html.fromstring(content)

        for element in document.cssselect(addon.configuration["css_selector"]):
            text = element.text
            if (
                element.getchildren()
                or element.tag in IGNORED_TAGS
                or not text
                or not text.strip()
                or text in source_units
                or text in units
            ):
                continue
            units.append(text)

    # Actually create units
    for text in units:
        source_translation.add_unit(
            request=None,
            context=calculate_checksum(text),
            source=text,
            target=None,
            author=addon.addon.user,
        )

    if errors:
        component.add_alert("CDNAddonError", occurrences=errors)
    else:
        component.delete_alert("CDNAddonError")


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
@transaction.atomic
def language_consistency(
    addon_id: int,
    language_ids: list[int],
    project_id: int,
    activity_log_id: int | None = None,
) -> None:
    try:
        addon = Addon.objects.get(pk=addon_id)
    except Addon.DoesNotExist:
        return
    project = Project.objects.get(pk=project_id)
    languages = Language.objects.filter(id__in=language_ids)
    request = HttpRequest()
    request.user = addon.addon.user

    # Filter components with missing translation
    components = project.component_set.annotate(
        translation_count=Count(
            "translation", filter=Q(translation__language__in=languages)
        )
    ).exclude(translation_count=languages.count())

    log_result: list[str] = []

    for component in components.iterator():
        # Avoid two language consistency add-ons working at same on a single component
        with component.lock:
            missing = languages.exclude(
                Q(translation__component=component) | Q(component=component)
            )
            if not missing:
                continue
            component.commit_pending("language consistency", None)
            for language in missing:
                new_lang = component.add_new_language(
                    language,
                    request,
                    send_signal=False,
                    create_translations=False,
                )
                if new_lang is None:
                    log_result.append(
                        f"{component.full_slug}: Could not add {language} language consistency: {component.new_lang_error_message}"
                    )
                else:
                    log_result.append(
                        f"{component.full_slug}: Added {language} for language consistency"
                    )
            try:
                component.create_translations_immediate()
            except FileParseError as error:
                log_result.append(
                    f"{component.full_slug}: Could not parse translation files: {error}"
                )

    if activity_log_id and log_result:
        update_addon_activity_log(activity_log_id, "\n".join(log_result))


@app.task(trail=False)
def daily_addons(modulo: bool = True) -> None:
    def daily_callback(
        addon: Addon, component: Component, *, activity_log_id: int | None = None
    ) -> None:
        addon.addon.daily(component, activity_log_id=activity_log_id)

    today = timezone.now()
    addons = Addon.objects.filter(event__event=AddonEvent.EVENT_DAILY)
    if modulo:
        addons = addons.annotate(hourmod=F("id") % 24).filter(hourmod=today.hour)
    handle_addon_event(
        AddonEvent.EVENT_DAILY,
        daily_callback,
        addon_queryset=addons,
        auto_scope=True,
    )


def update_addon_activity_log(
    pk: int, result: str = "", error_occurred: bool = False, pending: bool | None = None
) -> None:
    addon_activity_log = AddonActivityLog.objects.select_for_update().get(id=pk)
    addon_activity_log.details["error"] = error_occurred
    if result:
        addon_activity_log.update_result(result)
    if pending is not None:
        addon_activity_log.pending = pending
    addon_activity_log.save(update_fields=["details", "pending"])


@app.task(trail=False)
def cleanup_addon_activity_log() -> None:
    """Cleanup old add-on activity log entries."""
    from weblate.addons.models import AddonActivityLog

    AddonActivityLog.objects.filter(
        created__lt=now() - timedelta(days=settings.ADDON_ACTIVITY_LOG_EXPIRY)
    ).delete()


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=60,
)
@transaction.atomic
def postconfigure_addon(addon_id: int, addon=None) -> None:
    if addon is None:
        addon = Addon.objects.get(pk=addon_id)
    addon.addon.post_configure_run()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(crontab(minute=45), daily_addons.s(), name="daily-addons")
    sender.add_periodic_task(
        crontab(hour=0, minute=40),  # Not to run on minute 0 to spread the load
        cleanup_addon_activity_log.s(),
        name="cleanup-addon-activity-log",
    )


@app.task(trail=True)
def addon_change(change_ids: list[int], **kwargs) -> None:
    """
    Process add-on change events for a list of changes.

    This task retrieves add-ons that are subscribed to change events and
    applies the change event to each relevant add-on.
    """
    addons = Addon.objects.filter(event__event=AddonEvent.EVENT_CHANGE).select_related(
        "component", "project"
    )

    for change in Change.objects.filter(pk__in=change_ids).prefetch_for_render():
        change.fill_in_prefetched()
        # Filter addons for this change
        change_addons = [
            addon
            for addon in addons
            if (not addon.component or addon.component == change.component)
            and (not addon.project or addon.project == change.project)
        ]
        if change_addons:
            handle_addon_event(
                AddonEvent.EVENT_CHANGE,
                "change_event",
                (change,),
                addon_queryset=change_addons,
                project=change.project,
                component=change.component,
                translation=change.translation,
            )
