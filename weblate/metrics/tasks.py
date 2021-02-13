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
from datetime import date, timedelta

from celery.schedules import crontab

from weblate.auth.models import User
from weblate.memory.models import Memory
from weblate.metrics.models import Metric
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Change, Component, Project, Translation
from weblate.utils.celery import app
from weblate.utils.stats import GlobalStats

BASIC_KEYS = {
    "all",
    "all_words",
    "translated",
    "translated_words",
    "approved",
    "approved_words",
    "allchecks",
    "allchecks_words",
    "suggestions",
    "suggestions_words",
    "comments",
    "comments_words",
    "languages",
}
SOURCE_KEYS = BASIC_KEYS | {
    "source_strings",
    "source_words",
}


def collect_global():
    stats = GlobalStats()
    data = {
        "projects": Project.objects.count(),
        "components": Component.objects.count(),
        "translations": Translation.objects.count(),
        "memory": Memory.objects.count(),
        "screenshots": Screenshot.objects.count(),
        "changes": Change.objects.filter(
            timestamp__date=date.today() - timedelta(days=1)
        ).count(),
        "users": User.objects.count(),
    }

    for key in SOURCE_KEYS:
        data[key] = getattr(stats, key)

    Metric.objects.bulk_create(
        [
            Metric(scope=Metric.SCOPE_GLOBAL, relation=0, name=name, value=value)
            for name, value in data.items()
        ]
    )


@app.task(trail=False)
def collect_metrics():
    collect_global()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
