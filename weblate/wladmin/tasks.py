# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.tasks import run_backup_preparation
from weblate.wladmin.models import BackupService, SecurityScan, SupportStatus

if TYPE_CHECKING:
    from celery import Celery


def run_backup_service(service: BackupService) -> bool:
    if not service.ensure_init():
        return False
    service.backup()
    service.prune()
    today = timezone.now().date()
    if today.weekday() == 3:
        service.cleanup()
    return True


@app.task(trail=False)
@transaction.atomic
def support_status_update() -> None:
    for support in SupportStatus.objects.filter(enabled=True).select_for_update():
        support.refresh()
        support.save()


@app.task(trail=False, autoretry_for=(WeblateLockTimeoutError,))
def backup(service_ids: list[int] | None = None) -> None:
    if service_ids is None:
        service_ids = list(
            BackupService.objects.filter(enabled=True)
            .order_by("pk")
            .values_list("pk", flat=True)
        )

    run_backup_preparation(service_ids)
    for service_id in service_ids:
        backup_service.delay(service_id)


@app.task(trail=False, autoretry_for=(WeblateLockTimeoutError,))
def backup_service(pk: int) -> None:
    try:
        service = BackupService.objects.get(pk=pk)
    except BackupService.DoesNotExist:
        # The service was removed meanwhile
        return
    run_backup_service(service)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        900, cleanup_security_scans.s(), name="cleanup-security-scans"
    )
    # Randomize this per site to avoid all instances hitting server at the same time
    minute_to_run = hash(settings.SITE_DOMAIN) % 1440
    sender.add_periodic_task(
        crontab(hour=minute_to_run // 60, minute=minute_to_run % 60),
        support_status_update.s(),
        name="support-status-update",
    )
    sender.add_periodic_task(crontab(hour=2, minute=0), backup.s(), name="backup")


@app.task(trail=False, soft_time_limit=3500, time_limit=3600)
def security_scan_task(scan_id: str) -> None:
    from weblate.wladmin.security import run_security_scan  # ruff: ignore[import-outside-top-level]

    run_security_scan(scan_id)


@app.task(trail=False)
def cleanup_security_scans() -> None:
    from django.core.cache import cache  # ruff: ignore[import-outside-top-level]
    from django.utils.translation import gettext_noop  # ruff: ignore[import-outside-top-level]

    from weblate.wladmin.security import INPUT_TTL, input_key  # ruff: ignore[import-outside-top-level]

    expired = SecurityScan.objects.filter(
        state__in=["pending", "running", "configuring"],
        created__lt=timezone.now() - timedelta(seconds=INPUT_TTL),
    )
    for scan in expired:
        cache.delete(input_key(scan.pk))
    expired.update(
        state="failed",
        completed=timezone.now(),
        error=gettext_noop("The security operation expired. Start a new operation."),
    )
