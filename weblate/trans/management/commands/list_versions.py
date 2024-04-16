# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import platform
import sys

from django import db
from django.conf import settings

from weblate.utils.db import using_postgresql
from weblate.utils.management.base import BaseCommand
from weblate.utils.requirements import get_versions_list


class Command(BaseCommand):
    help = "lists versions of required software components"

    def write_item(self, prefix, value) -> None:
        self.stdout.write(f" * {prefix}: {value}")

    def handle(self, *args, **options) -> None:
        """Print versions of dependencies."""
        for version in get_versions_list():
            self.write_item(version[0], version[2])
        self.write_item(
            "Database backends",
            ", ".join(conn["ENGINE"] for conn in db.connections.databases.values()),
        )
        if using_postgresql():
            from django.db.backends.postgresql.psycopg_any import is_psycopg3

            if is_psycopg3:
                from psycopg.pq import __impl__

                pg_engine = f"psycopg3 ({__impl__})"
            else:
                pg_engine = "psycopg2"
            self.write_item("PostgreSQL implementation", pg_engine)

        self.write_item(
            "Cache backends",
            ", ".join(
                "{}:{}".format(key, value["BACKEND"].split(".")[-1])
                for key, value in settings.CACHES.items()
            ),
        )
        self.write_item(
            "Email setup", f"{settings.EMAIL_BACKEND}: {settings.EMAIL_HOST}"
        )
        self.write_item(
            "OS encoding",
            f"filesystem={sys.getfilesystemencoding()}, default={sys.getdefaultencoding()}",
        )
        self.write_item(
            "Celery",
            "{}, {}, {}".format(
                getattr(settings, "CELERY_BROKER_URL", "N/A"),
                getattr(settings, "CELERY_RESULT_BACKEND", "N/A"),
                "eager" if settings.CELERY_TASK_ALWAYS_EAGER else "regular",
            ),
        )
        self.write_item(
            "Platform",
            f"{platform.system()} {platform.release()} ({platform.machine()})",
        )
