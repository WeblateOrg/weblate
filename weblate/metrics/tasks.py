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

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.trans.models import Component, ComponentList, Project, Translation
from weblate.utils.celery import app
from weblate.utils.stats import prefetch_stats


@app.task(trail=False)
def collect_metrics():
    Metric.objects.collect_global()
    for project in prefetch_stats(Project.objects.all()):
        Metric.objects.collect_project(project)
    for component in prefetch_stats(Component.objects.all()):
        Metric.objects.collect_component(component)
    for clist in prefetch_stats(ComponentList.objects.all()):
        Metric.objects.collect_component_list(clist)
    for translation in prefetch_stats(Translation.objects.all()):
        Metric.objects.collect_translation(translation)
    for user in User.objects.filter(is_active=True):
        Metric.objects.collect_user(user)
    for language in prefetch_stats(Language.objects.all()):
        Metric.objects.collect_language(language)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
