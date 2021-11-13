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


from celery.schedules import crontab

from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeout
from weblate.wladmin.models import BackupService, SupportStatus


@app.task(trail=False)
def support_status_update():
    support = SupportStatus.objects.get_current()
    if support.secret:
        support.refresh()
        support.save()


@app.task(trail=False)
def backup():
    for service in BackupService.objects.filter(enabled=True):
        backup_service.delay(service.pk)


@app.task(trail=False, autoretry_for=(WeblateLockTimeout,))
def backup_service(pk):
    service = BackupService.objects.get(pk=pk)
    service.ensure_init()
    service.backup()
    service.prune()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        24 * 3600, support_status_update.s(), name="support-status-update"
    )
    sender.add_periodic_task(crontab(hour=2, minute=0), backup.s(), name="backup")
