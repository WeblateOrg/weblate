# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.utils import timezone

from weblate.metrics.models import (
    Metric,
    get_change_metric_data,
    get_language_change_metric_data,
)
from weblate.metrics.tasks import (
    METRIC_COLLECTION_TASKS,
    cleanup_metrics,
    collect_metrics,
)
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, ComponentLink, Project
from weblate.trans.models.change import Change
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.workspaces.models import Workspace


class MetricTestCase(FixtureComponentTestCase):
    def test_collect_schedules_scope_tasks(self) -> None:
        tasks = [MagicMock() for task in METRIC_COLLECTION_TASKS]
        with patch("weblate.metrics.tasks.METRIC_COLLECTION_TASKS", tasks):
            collect_metrics()

        date_value = timezone.now().date().isoformat()
        for task in tasks:
            task.delay.assert_called_once_with(date_value)

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

    def test_collect_uses_requested_date(self) -> None:
        collection_date = timezone.now().date() - timedelta(days=5)

        metric = Metric.objects.collect_component(self.component, collection_date)

        self.assertEqual(metric.date, collection_date)

    def test_change_metric_aggregates(self) -> None:
        Change.objects.all().delete()
        collection_date = timezone.now().date()
        old_user = create_another_user("-old-metric")
        yesterday = self.translation.change_set.create(
            action=ActionEvents.CHANGE, user=self.user
        )
        old = self.translation.change_set.create(
            action=ActionEvents.CHANGE, user=old_user
        )
        Change.objects.filter(pk=yesterday.pk).update(
            timestamp=timezone.now() - timedelta(days=1)
        )
        Change.objects.filter(pk=old.pk).update(
            timestamp=timezone.now() - timedelta(days=45)
        )

        with self.assertNumQueries(2):
            data = get_change_metric_data(
                self.component.change_set.all(), collection_date
            )
        with self.assertNumQueries(2):
            language_data = get_language_change_metric_data(
                self.component.change_set.all(), collection_date
            )[self.translation.language_id]

        expected = {"changes": 1, "contributors": 1, "contributors_total": 2}
        self.assertEqual(data, expected)
        self.assertEqual(language_data, expected)

    def test_collect_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Metrics workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])

        metric = Metric.objects.collect_workspace(workspace)

        self.assertEqual(metric.scope, Metric.SCOPE_WORKSPACE)
        self.assertEqual(metric.relation, workspace.metric_id)
        self.assertEqual(metric.dict_data["projects"], 1)
        self.assertEqual(metric.dict_data["components"], 1)
        self.assertEqual(
            metric.dict_data["translations"],
            self.component.translation_set.count(),
        )
        self.assertEqual(metric.dict_data["all"], self.project.stats.all)

    def test_workspace_metric_lifecycle(self) -> None:
        workspace = Workspace.objects.create(name="Metric lifecycle workspace")
        relation = workspace.metric_id

        self.assertTrue(
            Metric.objects.filter(
                scope=Metric.SCOPE_WORKSPACE,
                relation=relation,
            ).exists()
        )

        workspace.delete()

        self.assertFalse(
            Metric.objects.filter(
                scope=Metric.SCOPE_WORKSPACE,
                relation=relation,
            ).exists()
        )

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
