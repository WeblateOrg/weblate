# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

from django.apps import apps
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from weblate.auth.models import User
from weblate.metrics.models import (
    Metric,
    get_change_metric_data,
    get_language_change_metric_data,
)
from weblate.metrics.tasks import (
    METRIC_COLLECTION_TASKS,
    cleanup_metrics,
    collect_metrics,
    collect_user_metrics,
)
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, ComponentLink, Project
from weblate.trans.models.change import Change, dt_as_day_range
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Callable


class MetricTestCase(FixtureComponentTestCase):
    def test_collect_users(self) -> None:
        collection_date = timezone.now().date() - timedelta(days=5)
        start, end = dt_as_day_range(collection_date - timedelta(days=1))
        other = create_another_user("-metrics-bot")
        idle = create_another_user("-metrics-idle")
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        User.objects.filter(pk=other.pk).update(is_bot=True)
        actions = (
            ActionEvents.COMMENT,
            ActionEvents.SUGGESTION,
            ActionEvents.CHANGE,
            ActionEvents.SCREENSHOT_ADDED,
            ActionEvents.SCREENSHOT_UPLOADED,
            ActionEvents.UPDATE,
        )
        for action in actions:
            change = self.translation.change_set.create(action=action, user=self.user)
            Change.objects.filter(pk=change.pk).update(timestamp=start)
        for timestamp in (
            start,
            end,
            start - timedelta(microseconds=1),
            end + timedelta(microseconds=1),
        ):
            change = self.translation.change_set.create(
                action=ActionEvents.COMMENT, user=self.user
            )
            Change.objects.filter(pk=change.pk).update(timestamp=timestamp)
        change = self.translation.change_set.create(action=ActionEvents.NEW, user=other)
        Change.objects.filter(pk=change.pk).update(timestamp=start)

        users = [self.user, other, idle]
        expected = {
            self.user.pk: (
                8,
                {"comments": 3, "suggestions": 1, "translations": 1, "screenshots": 2},
            ),
            other.pk: (1, {"translations": 1}),
            idle.pk: (0, {}),
        }
        metrics = Metric.objects.filter(
            scope=Metric.SCOPE_USER,
            relation__in=[user.pk for user in users],
            date=collection_date,
        )
        Metric.objects.collect_users([user.pk for user in users], collection_date)

        self.assertEqual(metrics.count(), len(users))
        for metric in metrics:
            changes, data = expected[metric.relation]
            self.assertEqual(metric.changes, changes)
            self.assertTrue(metric.data)
            self.assertEqual(
                {key: value for key, value in metric.dict_data.items() if value}, data
            )

    def test_collect_users_preserves_existing_metrics(self) -> None:
        collection_date = timezone.now().date() - timedelta(days=5)
        users = [create_another_user(f"-metrics-{index}") for index in range(3)]
        for user, data in zip(users, (None, [], [42]), strict=True):
            Metric.objects.create(
                scope=Metric.SCOPE_USER,
                relation=user.pk,
                date=collection_date,
                changes=17,
                data=data,
            )
        unrelated = [
            Metric.objects.create(
                scope=scope,
                relation=users[0].pk,
                secondary=secondary,
                date=date,
                changes=23,
            )
            for scope, secondary, date in (
                (Metric.SCOPE_USER, 0, collection_date - timedelta(days=1)),
                (Metric.SCOPE_USER, 1, collection_date),
                (Metric.SCOPE_PROJECT, 0, collection_date),
            )
        ]

        for _ in range(2):
            Metric.objects.collect_users([user.pk for user in users], collection_date)
            for index, user in enumerate(users):
                metric = Metric.objects.get(
                    scope=Metric.SCOPE_USER,
                    relation=user.pk,
                    secondary=0,
                    date=collection_date,
                )
                self.assertEqual(metric.changes, 17)
                self.assertIsNotNone(metric.data)
                if index == 2:
                    self.assertEqual(metric.data, [42])
                else:
                    self.assertTrue(metric.data)
                    self.assertFalse(any(metric.data or []))
        for metric in unrelated:
            metric.refresh_from_db()
            self.assertEqual(metric.changes, 23)
            self.assertIsNone(metric.data)

    def test_collect_users_queries(self) -> None:
        collection_date = timezone.now().date() - timedelta(days=5)
        users = [self.user, create_another_user("-metrics-queries")]
        for count in (1, 2):
            for data, expected_queries in (
                ("missing", 3),
                (None, 4),
                ([], 4),
                ([42], 3),
            ):
                with self.subTest(count=count, data=data):
                    Metric.objects.filter(
                        scope=Metric.SCOPE_USER, date=collection_date
                    ).delete()
                    if data != "missing":
                        Metric.objects.bulk_create(
                            [
                                Metric(
                                    scope=Metric.SCOPE_USER,
                                    relation=user.pk,
                                    date=collection_date,
                                    changes=0,
                                    data=data,
                                )
                                for user in users[:count]
                            ]
                        )
                    with CaptureQueriesContext(connection) as queries:
                        Metric.objects.collect_users(
                            [user.pk for user in users[:count]], collection_date
                        )
                    statements = [
                        query["sql"]
                        for query in queries
                        if query["sql"].startswith(("SELECT", "INSERT", "UPDATE"))
                    ]
                    self.assertEqual(len(statements), expected_queries)
                    self.assertEqual(
                        sum('FROM "trans_change"' in sql for sql in statements), 1
                    )

        with self.assertNumQueries(0):
            Metric.objects.collect_users([], collection_date)

    def test_collect_user_metrics_batches(self) -> None:
        # Bulk creation avoids unrelated user initialization work in this test.
        User.objects.bulk_create(
            [User(username=f"metrics-batch-{index}") for index in range(501)]
        )
        user_ids = list(User.objects.order_by("pk").values_list("pk", flat=True))
        collection_date = timezone.now().date() - timedelta(days=5)
        with (
            patch("weblate.metrics.tasks.Metric.objects.collect_users") as collect,
            patch("weblate.metrics.tasks._log_finished") as finished,
        ):
            collect_user_metrics(collection_date.isoformat())
        self.assertEqual(
            collect.call_args_list,
            [
                call(tuple(user_ids[index : index + 500]), collection_date)
                for index in range(0, len(user_ids), 500)
            ],
        )
        self.assertEqual(
            finished.call_args.args[:3], ("user", collection_date, len(user_ids))
        )

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


class UserMetricConcurrencyTest(TransactionTestCase):
    def test_overlapping_collectors_missing_metric(self) -> None:
        self.check_overlapping_collectors(None, missing=True)

    def test_overlapping_collectors_initialized_metric(self) -> None:
        self.check_overlapping_collectors(None)

    def test_overlapping_collectors_empty_data(self) -> None:
        self.check_overlapping_collectors([])

    def check_overlapping_collectors(
        self, initial: list[int] | None, *, missing: bool = False
    ) -> None:
        collection_date = timezone.now().date() - timedelta(days=5)
        user = create_another_user("-metrics-concurrent")
        metrics = Metric.objects.filter(
            scope=Metric.SCOPE_USER,
            relation=user.pk,
            secondary=0,
            date=collection_date,
        )
        if not missing:
            metrics.create(
                scope=Metric.SCOPE_USER,
                relation=user.pk,
                date=collection_date,
                changes=17,
                data=initial,
            )
        completed = Event()
        inserting = Event()
        release = Event()
        finished = Event()

        def first_collector() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    Metric.objects.collect_users([user.pk], collection_date)
                    metrics.update(data=[42])
                    completed.set()
                    self.assertTrue(release.wait(10))
            finally:
                connection.close()

        def observe_insert(
            execute: Callable[..., object],
            sql: str,
            params: object,
            many: bool,
            context: dict[str, object],
        ) -> object:
            if sql.startswith('INSERT INTO "metrics_metric"'):
                inserting.set()
            return execute(sql, params, many, context)

        def second_collector() -> None:
            close_old_connections()
            try:
                with connection.execute_wrapper(observe_insert):
                    Metric.objects.collect_users([user.pk], collection_date)
                finished.set()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(first_collector)
            try:
                self.assertTrue(completed.wait(10))
                second = executor.submit(second_collector)
                self.assertTrue(inserting.wait(10))
                self.assertFalse(finished.wait(0.1))
            finally:
                release.set()
            first.result(timeout=10)
            second.result(timeout=10)
        metric = metrics.get()
        self.assertEqual(metric.data, [42])
        self.assertEqual(metric.changes, 0 if missing else 17)
