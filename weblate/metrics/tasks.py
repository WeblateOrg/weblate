# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
def collect_metrics() -> None:
    Metric.objects.collect_global()
    for project in prefetch_stats(Project.objects.all()):
        Metric.objects.collect_project(project)
    for component in prefetch_stats(Component.objects.all()):
        Metric.objects.collect_component(component)
    for clist in prefetch_stats(ComponentList.objects.all()):
        Metric.objects.collect_component_list(clist)
    for translation in prefetch_stats(Translation.objects.all()):
        Metric.objects.collect_translation(translation)
    for user in User.objects.filter():
        Metric.objects.collect_user(user)
    for language in prefetch_stats(Language.objects.all()):
        Metric.objects.collect_language(language)


@app.task(trail=False)
def cleanup_metrics() -> None:
    """Remove stale metrics."""
    today = timezone.now().date()
    # Remove past metrics, but we need data for last 24 months
    Metric.objects.filter(date__lte=today - timedelta(days=800)).delete()

    # Remove detailed data for past metrics, we need details only for two months
    # - avoid filtering on data field as that one is not indexed
    # - wipe only interval of data with assumption that this task is executed daily
    Metric.objects.filter(
        date__range=(today - timedelta(days=75), today - timedelta(days=65))
    ).update(data=None)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
    sender.add_periodic_task(
        crontab(hour=23, minute=1), cleanup_metrics.s(), name="cleanup-metrics"
    )
