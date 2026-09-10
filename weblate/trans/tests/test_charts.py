# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for charts and widgets."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.tests.test_views import FixtureTestCase


class ChartsTest(FixtureTestCase):
    """Testing of charts."""

    def test_activity_monthly(self) -> None:
        """Test of monthly activity charts."""
        response = self.client.get(reverse("monthly_activity_json"))
        self.assertEqual(len(response.json()), 52)

    def test_monthly_activity_cold_cache_uses_single_metric_query(self) -> None:
        """Cold cache month aggregation should be loaded in one query."""
        cache.clear()

        last_month = timezone.now().date().replace(day=1) - timedelta(days=1)
        month_start = date(last_month.year, last_month.month, 1)
        zero_month = month_start - timedelta(days=1)
        previous_year = last_month.year - 1
        previous_month_end = date(
            previous_year,
            last_month.month,
            monthrange(previous_year, last_month.month)[1],
        )

        Metric.objects.filter(
            scope=Metric.SCOPE_TRANSLATION,
            relation=self.translation.pk,
        ).delete()
        Metric.objects.bulk_create(
            [
                Metric(
                    scope=Metric.SCOPE_TRANSLATION,
                    relation=self.translation.pk,
                    secondary=0,
                    date=month_start,
                    changes=2,
                ),
                Metric(
                    scope=Metric.SCOPE_TRANSLATION,
                    relation=self.translation.pk,
                    secondary=0,
                    date=last_month,
                    changes=3,
                ),
                Metric(
                    scope=Metric.SCOPE_TRANSLATION,
                    relation=self.translation.pk,
                    secondary=0,
                    date=previous_month_end,
                    changes=4,
                ),
                Metric(
                    scope=Metric.SCOPE_TRANSLATION,
                    relation=self.translation.pk,
                    secondary=0,
                    date=zero_month,
                    changes=0,
                ),
            ]
        )

        wrapper = MetricsWrapper(
            self.translation,
            Metric.SCOPE_TRANSLATION,
            self.translation.pk,
        )
        with self.assertNumQueries(1):
            activity = wrapper.monthly_activity

        self.assertEqual(activity[-1]["current"], 5)
        self.assertEqual(activity[-1]["previous"], 4)
        self.assertEqual(activity[-2]["current"], 0)
        self.assertEqual(activity[-2]["previous"], 0)

        warm_wrapper = MetricsWrapper(
            self.translation, Metric.SCOPE_TRANSLATION, self.translation.pk
        )
        with self.assertNumQueries(0):
            self.assertEqual(warm_wrapper.monthly_activity, activity)
            totals = warm_wrapper.monthly_activity_totals
        self.assertEqual(totals[zero_month.year, zero_month.month], 0)
        self.assertEqual(totals[zero_month.year - 1, zero_month.month], 0)

        cache.delete(wrapper.get_month_cache_key(last_month.year, last_month.month))
        partial_wrapper = MetricsWrapper(
            self.translation, Metric.SCOPE_TRANSLATION, self.translation.pk
        )
        with self.assertNumQueries(1):
            self.assertEqual(partial_wrapper.monthly_activity, activity)
