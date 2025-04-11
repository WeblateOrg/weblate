# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import gzip
import os
import shutil
import subprocess
import sys
import time
from importlib import import_module
from shutil import copyfile

from celery.schedules import crontab
from django.conf import settings
from django.core.cache import cache
from django.core.management.commands import diffsettings
from ruamel.yaml import YAML

import weblate.utils.version
from weblate.formats.models import FILE_FORMATS
from weblate.logger import LOGGER
from weblate.machinery.models import MACHINERY
from weblate.trans.models import Component, Translation
from weblate.trans.util import get_clean_env
from weblate.utils.backup import backup_lock
from weblate.utils.celery import app
from weblate.utils.data import data_dir
from weblate.utils.db import using_postgresql
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.vcs.models import VCS_REGISTRY

from .const import HEARTBEAT_FREQUENCY


@app.task(trail=False)
def ping():
    return {
        "version": weblate.utils.version.GIT_VERSION,
        "vcs": sorted(VCS_REGISTRY.keys()),
        "formats": sorted(FILE_FORMATS.keys()),
        "mt_services": sorted(MACHINERY.keys()),
        "encoding": [sys.getfilesystemencoding(), sys.getdefaultencoding()],
        "uid": os.getuid(),
        "data_dir": settings.DATA_DIR,
    }


@app.task(trail=False)
def heartbeat() -> None:
    cache.set("celery_loaded", time.time())
    cache.set("celery_heartbeat", time.time())
    cache.set(
        "celery_encoding", [sys.getfilesystemencoding(), sys.getdefaultencoding()]
    )


@app.task(trail=False, autoretry_for=(WeblateLockTimeoutError,))
def settings_backup() -> None:
    with backup_lock():
        # Expand settings in case it contains non-trivial code
        command = diffsettings.Command()
        kwargs = {"default": None, "all": False, "output": "hash"}
        with open(data_dir("backups", "settings-expanded.py"), "w") as handle:
            handle.write(command.handle(**kwargs))

        # Backup original settings
        if settings.SETTINGS_MODULE:
            settings_mod = import_module(settings.SETTINGS_MODULE)
            if settings_mod.__file__ is not None:
                copyfile(settings_mod.__file__, data_dir("backups", "settings.py"))

        # Backup environment (to make restoring Docker easier)
        with open(data_dir("backups", "environment.yml"), "w") as handle:
            yaml = YAML()
            yaml.dump(dict(os.environ), handle)


@app.task(trail=False)
def update_translation_stats_parents(pk: int) -> None:
    translation = Translation.objects.get(pk=pk)
    translation.stats.update_parents()


@app.task(trail=False)
def update_language_stats_parents(pk: int) -> None:
    component = Component.objects.get(pk=pk)
    component.stats.update_language_stats_parents()


@app.task(trail=False, autoretry_for=(WeblateLockTimeoutError,))
def database_backup() -> None:
    if settings.DATABASE_BACKUP == "none":
        return
    with backup_lock():
        database = settings.DATABASES["default"]
        env = get_clean_env()
        compress = settings.DATABASE_BACKUP == "compressed"

        out_compressed = data_dir("backups", "database.sql.gz")
        out_text = data_dir("backups", "database.sql")

        if using_postgresql():
            cmd = [
                "pg_dump",
                # Superuser only, crashes on Alibaba Cloud Database PolarDB
                "--no-subscriptions",
                "--clean",
                "--if-exists",
                "--dbname",
                database["NAME"],
            ]

            if database["HOST"]:
                cmd.extend(["--host", database["HOST"]])
            if database["PORT"]:
                cmd.extend(["--port", database["PORT"]])
            if database["USER"]:
                cmd.extend(["--username", database["USER"]])
            if settings.DATABASE_BACKUP == "compressed":
                cmd.extend(["--file", out_compressed])
                cmd.extend(["--compress", "6"])
                compress = False
            else:
                cmd.extend(["--file", out_text])

            env["PGPASSWORD"] = database["PASSWORD"]
        else:
            cmd = [
                "mysqldump",
                "--result-file",
                out_text,
                "--single-transaction",
                "--skip-lock-tables",
            ]

            if database["HOST"]:
                cmd.extend(["--host", database["HOST"]])
            if database["PORT"]:
                cmd.extend(["--port", database["PORT"]])
            if database["USER"]:
                cmd.extend(["--user", database["USER"]])

            cmd.extend(["--databases", database["NAME"]])

            env["MYSQL_PWD"] = database["PASSWORD"]

        try:
            subprocess.run(
                cmd,  # type: ignore[arg-type]
                env=env,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            add_breadcrumb(
                category="backup",
                message="database dump output",
                stdout=error.stdout,
                stderr=error.stderr,
            )
            LOGGER.error("failed database backup: %s", error.stderr)
            report_error("Database backup failed")
            raise

        if compress:
            with open(out_text, "rb") as f_in, gzip.open(out_compressed, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.unlink(out_text)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    cache.set("celery_loaded", time.time())
    sender.add_periodic_task(
        crontab(hour=1, minute=0), settings_backup.s(), name="settings-backup"
    )
    sender.add_periodic_task(
        crontab(hour=1, minute=30), database_backup.s(), name="database-backup"
    )
    sender.add_periodic_task(HEARTBEAT_FREQUENCY, heartbeat.s(), name="heartbeat")
