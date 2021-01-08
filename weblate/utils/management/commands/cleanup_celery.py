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
            self.stderr.write(f"Removing corrupted schedule file: {error!r}")
            self.try_remove(settings.CELERY_BEAT_SCHEDULE_FILENAME)
            self.try_remove(settings.CELERY_BEAT_SCHEDULE_FILENAME + ".db")
            self.setup_schedule()
