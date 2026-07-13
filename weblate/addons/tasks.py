# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import contextlib
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast

from celery.schedules import crontab
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpRequest
from django.utils import timezone
from django.utils.timezone import now
from lxml import html

from weblate.addons.events import (
    AddonActivityLogReason,
    AddonActivityLogStatus,
    AddonEvent,
)
from weblate.addons.models import (
    Addon,
    AddonActivityLog,
    handle_addon_event,
    handle_daily_addon_event,
    handle_scoped_addon_event,
)
from weblate.lang.models import Language
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import Change, Component, Project
from weblate.utils.celery import app
from weblate.utils.hash import calculate_checksum
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.requests import open_restricted_asset_url
from weblate.utils.validators import validate_filename

if TYPE_CHECKING:
    from weblate.addons.consistency import LanguageConsistencyAddon

IGNORED_TAGS = {"script", "style"}


def read_component_file(component: Component, filename: str) -> str:
    validate_filename(filename)
    resolved = component.repository.resolve_symlinks(filename)
    return Path(component.full_path, resolved).read_text(encoding="utf-8")


def parse_cdn_html(addon: Addon, component: Component) -> list[dict[str, str]]:
    source_translation = component.source_translation
    source_units = set(source_translation.unit_set.values_list("source", flat=True))
    units = []
    errors: list[dict[str, str]] = []

    for filename in addon.configuration["files"].splitlines():
        filename = filename.strip()
        try:
            if filename.startswith(("http://", "https://")):
                with open_restricted_asset_url(
                    "get",
                    filename,
                    allow_private_targets=not settings.ASSET_RESTRICT_PRIVATE,
                    allowed_domains=settings.ASSET_PRIVATE_ALLOWLIST,
                ) as handle:
                    content = handle.text
            else:
                content = read_component_file(component, filename)
        except (OSError, ValidationError, ValueError) as error:
            errors.append(
                {
                    "addon": addon.name,
                    "addon_id": str(addon.pk),
                    "filename": filename,
                    "error": str(error),
                }
            )
            continue

        document = html.fromstring(content)

        for element in document.cssselect(addon.configuration["css_selector"]):
            text = element.text
            if (
                len(element)  # has children
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
    return errors


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def cdn_parse_html(
    addon_id: int, component_id: int, activity_log_id: int | None = None
) -> None:
    try:
        addon = Addon.objects.get(pk=addon_id)
    except Addon.DoesNotExist:
        return

    component = Component.objects.get(pk=component_id)
    errors = parse_cdn_html(addon, component)
    if activity_log_id:
        update_addon_activity_log(
            activity_log_id,
            errors or None,
            status=(
                AddonActivityLogStatus.ERROR
                if errors
                else AddonActivityLogStatus.SUCCESS
            ),
        )


def enforce_language_consistency(
    addon: Addon,
    languages,
    fake_request: HttpRequest,
    components,
    log_result: list[str],
) -> bool:
    has_errors = False
    for component in components.iterator():
        # Keep the standard lock ordering: repository first, then component.
        # This avoids inverting the order used by create_translations().
        with component.repository.lock, component.lock:
            missing = languages.exclude(
                Q(translation__component=component) | Q(component=component)
            )
            if not missing:
                continue
            component.commit_pending("language consistency", None)
            for language in missing:
                component.refresh_lock()
                new_lang = component.add_new_language(
                    language,
                    fake_request,  # type: ignore[arg-type]
                    send_signal=False,
                    create_translations=False,
                )
                if new_lang is None:
                    has_errors = True
                    log_result.append(
                        f"{component.full_slug}: {addon.addon.verbose}: Could not add {language}: {component.new_lang_error_message}"
                    )
                else:
                    log_result.append(
                        f"{component.full_slug}: {addon.addon.verbose}: Added {language}"
                    )
            try:
                component.create_translations_immediate()
            except FileParseError as error:
                has_errors = True
                log_result.append(
                    f"{component.full_slug}: {addon.addon.verbose}: Could not parse translation files: {error}"
                )
    return has_errors


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def language_consistency(
    addon_id: int,
    language_ids: list[int],
    project_id: int | None = None,
    category_id: int | None = None,
    activity_log_id: int | None = None,
) -> None:
    log_result, has_errors = enforce_language_consistency_task(
        addon_id,
        language_ids,
        project_id=project_id,
        category_id=category_id,
    )
    if activity_log_id:
        update_addon_activity_log(
            activity_log_id,
            "\n".join(log_result) if log_result else None,
            status=(
                AddonActivityLogStatus.ERROR
                if has_errors
                else AddonActivityLogStatus.SUCCESS
            ),
        )


@transaction.atomic
def enforce_language_consistency_task(
    addon_id: int,
    language_ids: list[int],
    project_id: int | None = None,
    category_id: int | None = None,
) -> tuple[list[str], bool]:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Category

    if project_id is not None and category_id is not None:
        msg = "language_consistency cannot receive both project_id and category_id"
        raise ValueError(msg)

    try:
        addon = Addon.objects.get(pk=addon_id)
    except Addon.DoesNotExist:
        return [], False
    languages = Language.objects.filter(id__in=language_ids)
    fake_request = HttpRequest()
    fake_request.user = addon.addon.user

    project = None
    category = None

    # Filter components with missing translation
    if category_id is not None:
        category = Category.objects.get(pk=category_id)
    elif project_id is not None:
        project = Project.objects.get(pk=project_id)
    else:
        msg = "language_consistency requires either project_id or category_id"
        raise ValueError(msg)
    consistency_addon = cast("LanguageConsistencyAddon", addon.addon)
    components = consistency_addon.get_inconsistent_components(
        languages, project=project, category=category
    )

    log_result: list[str] = []

    has_errors = enforce_language_consistency(
        addon, languages, fake_request, components, log_result
    )
    return log_result, has_errors


@app.task(trail=False)
def daily_addons(modulo: bool = True) -> None:
    today = timezone.now()
    addons = Addon.objects.filter(event__event=AddonEvent.EVENT_DAILY).select_related(
        "component", "category", "project"
    )
    if modulo:
        addons = addons.annotate(hourmod=F("id") % 24).filter(hourmod=today.hour)
    handle_daily_addon_event(addons)


@app.task(trail=False)
def run_addon_manually(addon_id: int) -> None:
    try:
        addon = Addon.objects.select_related("component", "category", "project").get(
            pk=addon_id
        )
    except Addon.DoesNotExist:
        return

    if not addon.can_run_manually:
        return

    handle_scoped_addon_event([addon], AddonEvent.EVENT_MANUAL, "manual")


def update_addon_activity_log(
    pk: int,
    result: object | None = None,
    status: AddonActivityLogStatus | None = None,
    reason: AddonActivityLogReason | None = None,
    task_count: int | None = None,
) -> None:
    with transaction.atomic(savepoint=False):
        try:
            addon_activity_log = AddonActivityLog.objects.select_for_update().get(id=pk)
        except AddonActivityLog.DoesNotExist:
            # The log entry can disappear while an async add-on task is queued or
            # retrying, for example when the triggering component or add-on is
            # deleted and cascades the activity row away.
            return
        if task_count is None:
            addon_activity_log.update_activity(result, status=status, reason=reason)
        else:
            update_fanout_activity_log(
                addon_activity_log,
                result,
                status=(
                    status if status is not None else AddonActivityLogStatus.SUCCESS
                ),
                reason=reason,
                task_count=task_count,
            )
        addon_activity_log.save(update_fields=["details", "status"])


def update_fanout_activity_log(
    activity_log: AddonActivityLog,
    result: object | None,
    *,
    status: AddonActivityLogStatus,
    reason: AddonActivityLogReason | None,
    task_count: int,
) -> None:
    """Record one task result and finalize after the entire fan-out completes."""
    if task_count < 1:
        msg = "task_count must be positive"
        raise ValueError(msg)

    details = activity_log.details or {}
    progress = details.get("task_progress")
    if not isinstance(progress, dict):
        progress = {
            "total": task_count,
            "completed": 0,
            "success": 0,
            "error": 0,
            "skipped": 0,
        }
        details["task_progress"] = progress
    activity_log.details = details
    activity_log.update_activity(result)

    status = AddonActivityLogStatus(status)
    status_key = status.name.lower()
    progress["total"] = task_count
    progress["completed"] = int(progress.get("completed", 0)) + 1
    progress[status_key] = int(progress.get(status_key, 0)) + 1
    if status == AddonActivityLogStatus.SKIPPED and reason is not None:
        progress.setdefault("reason", reason.value)

    if progress["completed"] < task_count:
        activity_log.update_activity(status=AddonActivityLogStatus.PENDING)
        return

    if progress.get("error"):
        final_status = AddonActivityLogStatus.ERROR
    elif progress.get("success"):
        final_status = AddonActivityLogStatus.SUCCESS
    elif progress.get("skipped"):
        final_status = AddonActivityLogStatus.SKIPPED
    else:
        final_status = AddonActivityLogStatus.PENDING

    final_reason = None
    if final_status == AddonActivityLogStatus.SKIPPED:
        reason_value = progress.get("reason")
        if isinstance(reason_value, str):
            with contextlib.suppress(ValueError):
                final_reason = AddonActivityLogReason(reason_value)
    activity_log.update_activity(status=final_status, reason=final_reason)


@app.task(trail=False)
def cleanup_addon_activity_log() -> None:
    """Cleanup old add-on activity log entries."""
    AddonActivityLog.objects.filter(
        created__lt=now() - timedelta(days=settings.ADDON_ACTIVITY_LOG_EXPIRY)
    ).delete()


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=60,
)
@transaction.atomic
def postconfigure_addon(addon_id: int, addon: Addon | None = None) -> None:
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
    addons = list(Addon.objects.filter(event__event=AddonEvent.EVENT_CHANGE))
    category_ids_cache: dict[int | None, set[int]] = {None: set()}

    def get_category_ids(change: Change) -> set[int]:
        if change.category_id not in category_ids_cache:
            category = change.category
            category_ids: set[int] = set()
            while category is not None:
                category_ids.add(category.pk)
                category = category.category
            category_ids_cache[change.category_id] = category_ids
        return category_ids_cache[change.category_id]

    for change in Change.objects.filter(pk__in=change_ids).prefetch_for_render():
        change.fill_in_prefetched()
        # Filter addons for this change
        change_addons = [
            addon
            for addon in addons
            if (addon.component_id is None or addon.component_id == change.component_id)
            and (addon.project_id is None or addon.project_id == change.project_id)
            and (
                addon.category_id is None
                or (
                    # to ensure that addons configured on ancestor categories
                    # are also considered
                    change.component_id is not None
                    and addon.category_id in get_category_ids(change)
                )
            )
            and addon.addon.check_change_action(change)
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
