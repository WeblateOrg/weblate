# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.metrics.models import Metric
from weblate.metrics.tasks import cleanup_metrics, collect_metrics
from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureTestCase


class MetricTestCase(FixtureTestCase):
    def test_collect(self) -> None:
        collect_metrics()
        self.assertNotEqual(Metric.objects.count(), 0)

    def test_collect_global(self) -> None:
        Metric.objects.collect_global()
        self.assertNotEqual(Metric.objects.count(), 0)

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
