# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib
from datetime import timedelta

from django.apps import apps
from django.utils import timezone

from weblate.metrics.models import Metric
from weblate.metrics.tasks import cleanup_metrics, collect_metrics
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, ComponentLink, Project
from weblate.trans.models.change import Change
from weblate.trans.tests.test_views import FixtureComponentTestCase


class MetricTestCase(FixtureComponentTestCase):
    def test_collect(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Metrics", slug="metrics"
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        collect_metrics()
        self.assertNotEqual(Metric.objects.count(), 0)
        self.assertTrue(
            Metric.objects.filter(
                scope=Metric.SCOPE_CATEGORY,
                relation=category.pk,
                data__isnull=False,
            ).exists()
        )
        self.assertTrue(
            Metric.objects.filter(
                scope=Metric.SCOPE_CATEGORY_LANGUAGE,
                relation=category.pk,
                data__isnull=False,
            ).exists()
        )

    def test_collect_nested_shared_category(self) -> None:
        Change.objects.all().delete()
        other = Project.objects.create(name="Metrics target", slug="metrics-target")
        parent = Category.objects.create(
            project=other, name="Metrics parent", slug="metrics-parent"
        )
        child = Category.objects.create(
            project=other,
            category=parent,
            name="Metrics child",
            slug="metrics-child",
        )
        ComponentLink.objects.create(
            component=self.component, project=other, category=child
        )
        change = self.translation.change_set.create(
            action=ActionEvents.CHANGE, user=self.user
        )
        Change.objects.filter(pk=change.pk).update(
            timestamp=timezone.now() - timedelta(days=1)
        )
        Metric.objects.filter(scope=Metric.SCOPE_CATEGORY, relation=parent.pk).delete()

        metric = Metric.objects.collect_category(parent)
        self.assertEqual(metric.dict_data["components"], 1)
        self.assertEqual(
            metric.dict_data["translations"], self.component.translation_set.count()
        )
        self.assertEqual(metric.dict_data["all"], self.component.stats.all)
        self.assertEqual(metric.changes, 1)
        self.assertEqual(metric.dict_data["contributors"], 1)
        self.assertEqual(metric.dict_data["contributors_total"], 1)
        for language in parent.languages:
            language_metric = Metric.objects.get(
                scope=Metric.SCOPE_CATEGORY_LANGUAGE,
                relation=parent.pk,
                secondary=language.pk,
                data__isnull=False,
            )
            expected = int(language == self.translation.language)
            self.assertEqual(language_metric.changes, expected)
            self.assertEqual(language_metric.dict_data["contributors"], expected)
            self.assertEqual(language_metric.dict_data["contributors_total"], expected)

    def test_cleanup_legacy_category_language_metric_keys(self) -> None:
        migration = importlib.import_module(
            "weblate.metrics.migrations.0003_cleanup_category_language_metric_keys"
        )
        legacy = Metric.objects.create(
            scope=Metric.SCOPE_CATEGORY_LANGUAGE,
            relation=self.project.pk,
            secondary=self.translation.language_id,
            changes=0,
            data={},
        )
        retained = Metric.objects.create(
            scope=Metric.SCOPE_PROJECT,
            relation=self.project.pk,
            changes=0,
            data={},
        )

        migration.cleanup_category_language_metrics(apps, None)

        self.assertFalse(Metric.objects.filter(pk=legacy.pk).exists())
        self.assertTrue(Metric.objects.filter(pk=retained.pk).exists())

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
