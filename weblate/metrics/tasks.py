#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from datetime import timedelta

from celery.schedules import crontab
from django.utils import timezone

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


@app.task(trail=False)
def cleanup_metrics():
    """Remove stale metrics."""
    # Remove metrics for deleted objects
    projects = Project.objects.values_list("pk", flat=True)
    Metric.objects.filter(scope=Metric.SCOPE_PROJECT).exclude(
        relation__in=projects
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_PROJECT_LANGUAGE).exclude(
        relation__in=projects
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_COMPONENT).exclude(
        relation__in=Component.objects.values_list("pk", flat=True)
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_TRANSLATION).exclude(
        relation__in=Translation.objects.values_list("pk", flat=True)
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_USER).exclude(
        relation__in=User.objects.values_list("pk", flat=True)
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_COMPONENT_LIST).exclude(
        relation__in=ComponentList.objects.values_list("pk", flat=True)
    ).delete()
    Metric.objects.filter(scope=Metric.SCOPE_LANGUAGE).exclude(
        relation__in=Language.objects.values_list("pk", flat=True)
    ).delete()

    # Remove past metrics, but we need data for last 24 months
    cutoff = timezone.now() - timedelta(days=800)
    Metric.objects.filter(date__lte=cutoff).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
    sender.add_periodic_task(
        crontab(hour=23, minute=1), cleanup_metrics.s(), name="cleanup-metrics"
    )
