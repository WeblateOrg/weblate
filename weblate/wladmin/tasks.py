# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.wladmin.models import BackupService, SupportStatus


@app.task(trail=False)
def support_status_update() -> None:
    support = SupportStatus.objects.get_current()
    if support.secret:
        support.refresh()
        support.save()


@app.task(trail=False)
def backup() -> None:
    for service in BackupService.objects.filter(enabled=True):
        backup_service.delay(service.pk)


@app.task(trail=False, autoretry_for=(WeblateLockTimeoutError,))
def backup_service(pk) -> None:
    service = BackupService.objects.get(pk=pk)
    service.ensure_init()
    service.backup()
    service.prune()
    today = timezone.now().date()
    if today.weekday() == 3:
        service.cleanup()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    # Randomize this per site to avoid all instances hitting server at the same time
    minute_to_run = hash(settings.SITE_DOMAIN) % 1440
    sender.add_periodic_task(
        crontab(hour=minute_to_run // 60, minute=minute_to_run % 60),
        support_status_update.s(),
        name="support-status-update",
    )
    sender.add_periodic_task(crontab(hour=2, minute=0), backup.s(), name="backup")
