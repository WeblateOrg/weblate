#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


import os
import subprocess
import time

from celery.schedules import crontab
from django.conf import settings
from django.core.cache import cache
from django.core.management.commands import diffsettings

from weblate.trans.util import get_clean_env
from weblate.utils.celery import app
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error


@app.task(trail=False)
def ping():
    return None


@app.task(trail=False)
def heartbeat():
    cache.set("celery_loaded", time.time())
    cache.set("celery_heartbeat", time.time())


def ensure_backup_dir():
    backup_dir = data_dir("backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)


@app.task(trail=False)
def settings_backup():
    ensure_backup_dir()
    filename = data_dir("backups", "settings.py")
    command = diffsettings.Command()
    kwargs = {"default": None, "all": False, "output": "hash"}
    with open(filename, "w") as handle:
        handle.write(command.handle(**kwargs))


@app.task(trail=False)
def database_backup():
    ensure_backup_dir()
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.postgresql":
        return
    cmd = ["pg_dump", "--dbname", database["NAME"]]
    if database["HOST"]:
        cmd += ["--host", database["HOST"]]
    if database["PORT"]:
        cmd += ["--port", database["PORT"]]
    if database["USER"]:
        cmd += ["--username", database["USER"]]
    if settings.DATABASE_BACKUP == "compressed":
        cmd += ["--file", data_dir("backups", "database.sql.gz")]
        cmd += ["--compress", "6"]
    else:
        cmd += ["--file", data_dir("backups", "database.sql")]

    try:
        subprocess.check_output(
            cmd,
            env=get_clean_env({"PGPASSWORD": database["PASSWORD"]}),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as error:
        report_error(extra_data={"stdout": error.stdout.decode()})


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    cache.set("celery_loaded", time.time())
    sender.add_periodic_task(
        crontab(hour=1, minute=0), settings_backup.s(), name="settings-backup"
    )
    if settings.DATABASE_BACKUP != "none":
        sender.add_periodic_task(
            crontab(hour=1, minute=30), database_backup.s(), name="database-backup"
        )
    sender.add_periodic_task(60, heartbeat.s(), name="heartbeat")
