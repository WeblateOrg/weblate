# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from celery.beat import Service
from django.conf import settings

from weblate.utils.celery import app
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "removes incompatible celery schedule file"

    @staticmethod
    def try_remove(filename):
        if os.path.exists(filename):
            os.remove(filename)

    @staticmethod
    def setup_schedule():
        service = Service(app=app)
        scheduler = service.get_scheduler()
        scheduler.setup_schedule()

    def handle(self, *args, **options):
        try:
            self.setup_schedule()
        except Exception as error:
            if os.path.exists(settings.CELERY_BEAT_SCHEDULE_FILENAME):
                self.stderr.write(f"Removing corrupted schedule file: {error!r}")
                self.try_remove(settings.CELERY_BEAT_SCHEDULE_FILENAME)
                self.try_remove(settings.CELERY_BEAT_SCHEDULE_FILENAME + ".db")
                self.setup_schedule()
