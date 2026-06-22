# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from django.utils import timezone

from weblate.metrics.models import Metric
from weblate.metrics.tasks import cleanup_metrics, collect_metrics
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureComponentTestCase


class MetricTestCase(FixtureComponentTestCase):
    def test_collect(self) -> None:
        collect_metrics()
        self.assertNotEqual(Metric.objects.count(), 0)

    def test_collect_global(self) -> None:
        Metric.objects.collect_global()
        self.assertNotEqual(Metric.objects.count(), 0)

    def test_wrapper_prefers_today_metric(self) -> None:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        scope = Metric.SCOPE_GLOBAL
        relation = 0
        Metric.objects.filter_metric(scope, relation).filter(
            date__in=(today, yesterday)
        ).delete()

        Metric.objects.create_metrics(
            {"changes": 1}, None, set(), scope, relation, date=yesterday
        )
        Metric.objects.create_metrics(
            {"changes": 2, "projects": 1},
            None,
            set(),
            scope,
            relation,
            date=today,
        )

        self.assertEqual(MetricsWrapper(None, scope, relation).projects, 1)

    def test_wrapper_fills_past_60_metric(self) -> None:
        today = timezone.now().date()
        scope = Metric.SCOPE_GLOBAL
        relation = 0
        dates = (
            today,
            today - timedelta(days=30),
            today - timedelta(days=60),
        )
        Metric.objects.filter_metric(scope, relation).filter(date__in=dates).delete()

        for metric_date, projects in zip(dates, (4, 2, 1), strict=True):
            Metric.objects.create_metrics(
                {"changes": 1, "projects": projects},
                None,
                set(),
                scope,
                relation,
                date=metric_date,
            )

        self.assertEqual(MetricsWrapper(None, scope, relation).trend_60_projects, 50)

    def test_cleanup(self) -> None:
        collect_metrics()
        count = Metric.objects.count()
        cleanup_metrics()
        self.assertEqual(count, Metric.objects.count())
        Project.objects.all().delete()
        cleanup_metrics()
        new_count = Metric.objects.count()
        self.assertNotEqual(count, new_count)
        self.assertNotEqual(0, new_count)
