# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import shutil
import stat
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from django.db import transaction

from weblate.addons.events import AddonActivityLogStatus, AddonEvent
from weblate.addons.models import Addon, AddonActivityLog
from weblate.addons.tasks import update_addon_activity_log
from weblate.kotlin_sdk.models import KotlinSDKCleanup
from weblate.kotlin_sdk.publication import Publication
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError

if TYPE_CHECKING:
    from celery import Celery

    from weblate.kotlin_sdk.models import KotlinSDKBuild

LOGGER = logging.getLogger(__name__)


def schedule_cleanup(
    path: Path, *, build: KotlinSDKBuild | None = None, using: str = "default"
) -> None:
    intent, _ = KotlinSDKCleanup.objects.using(using).get_or_create(
        path=str(path.absolute()), defaults={"build": build}
    )

    def cleanup() -> None:
        cleanup_publication(intent.pk, using=using)

    transaction.on_commit(cleanup, using=using, robust=True)


def cleanup_publication(cleanup_id: int, *, using: str = "default") -> None:
    # Match publication's lock ordering before locking the deletion intent.
    addon_id = (
        KotlinSDKCleanup.objects.using(using)
        .filter(pk=cleanup_id)
        .values_list("build__addon_id", flat=True)
        .first()
    )
    with transaction.atomic(using=using):
        if addon_id is not None:
            Addon.objects.using(using).select_for_update().filter(pk=addon_id).first()
        intent = (
            KotlinSDKCleanup.objects.using(using)
            .select_for_update()
            .filter(pk=cleanup_id)
            .first()
        )
        if intent is None:
            return
        path = Path(intent.path)
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                mode = None
            if mode is not None and stat.S_ISDIR(mode):
                shutil.rmtree(path)
            elif mode is not None:
                path.unlink()
        except OSError:
            LOGGER.exception("Kotlin SDK CDN cleanup failed for %s; will retry", path)
            return
        if (build := intent.build) is not None:
            build.set_artifacts(())
            for parent in (path.parent, path.parent.parent):
                with suppress(OSError):
                    parent.rmdir()
        intent.delete(using=using)


@app.task(trail=False)
def cleanup_publications() -> None:
    for cleanup_id in KotlinSDKCleanup.objects.values_list("pk", flat=True).iterator():
        cleanup_publication(cleanup_id)
    # Incompatible add-ons are skipped by normal component event dispatch.
    for addon in Addon.objects.filter(name="weblate.cdn.kotlin").select_related(
        "component"
    ):
        if addon.is_valid and not addon.addon.can_process(component=addon.component):
            Publication(addon).schedule()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        3600, cleanup_publications.s(), name="cleanup-kotlin-sdk-publications"
    )


@app.task(autoretry_for=(WeblateLockTimeoutError,), retry_backoff=60)
def publish_kotlin_sdk(addon_id: int) -> None:
    """Serialize publication workers without locking the component repository."""
    candidate = Addon.objects.select_related("component").filter(pk=addon_id).first()
    if candidate is None or candidate.component is None:
        return
    lock = WeblateLock(scope="kotlin-sdk", key=addon_id, slug=str(addon_id))
    with lock:
        with transaction.atomic():
            addon = Addon.objects.select_for_update().filter(pk=addon_id).first()
            if (
                addon is None
                or not addon.is_valid
                or addon.name != "weblate.cdn.kotlin"
            ):
                return
            # Registrations arriving between publication phases can queue another run.
            addon.state.pop("kotlin_pending", None)
            Addon.objects.filter(pk=addon.pk).update(state=addon.state)
            activity = AddonActivityLog.objects.create(
                addon=addon,
                component=addon.component,
                event=AddonEvent.EVENT_DAILY,
                status=AddonActivityLogStatus.PENDING,
            )
        try:
            outcome = Publication(addon, lock=lock).publish()
        except Exception as error:
            update_addon_activity_log(
                activity.pk, str(error), status=AddonActivityLogStatus.ERROR
            )
            raise
        update_addon_activity_log(
            activity.pk,
            outcome.result if outcome else None,
            status=outcome.status if outcome else AddonActivityLogStatus.SUCCESS,
        )
