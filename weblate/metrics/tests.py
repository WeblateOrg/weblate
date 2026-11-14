# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dt_date
from datetime import timedelta
from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

from django.apps import apps
from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from weblate.auth.models import User
from weblate.metrics.models import (
    SOURCE_KEYS,
    Metric,
    get_change_metric_data,
    get_language_change_metric_data,
)
from weblate.metrics.tasks import (
    METRIC_COLLECTION_TASKS,
    cleanup_metrics,
    collect_metrics,
    collect_project_metrics,
    collect_user_metrics,
)
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, ComponentLink, ComponentList, Project
from weblate.trans.models.change import Change, dt_as_day_range
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Callable


class MetricTestCase(FixtureComponentTestCase):
    def test_project_batches_commit_independently(self) -> None:
        """A retry can finish after a later batch fails without changing prior rows."""
        projects = Project.objects.bulk_create(
            [
                Project(name=f"Retry {index}", slug=f"retry-{index}")
                for index in range(3)
            ]
        )
        self.warm_metric_stats([self.project, *projects])
        self.warm_metric_stats(
            [ProjectLanguage(self.project, lang) for lang in self.project.languages]
        )
        date = timezone.now().date() - timedelta(days=5)
        collector = Metric.objects.collect_batch
        sizes = []

        def fail_second_batch(
            objects: tuple[Project, ...], collection_date: dt_date
        ) -> None:
            sizes.append(len(objects))
            if len(sizes) == 2:
                msg = "Interrupted collection"
                raise RuntimeError(msg)
            collector(objects, collection_date)

        with (
            patch("weblate.metrics.tasks.BATCH_SIZE", 2),
            patch(
                "weblate.metrics.tasks.Metric.objects.collect_batch",
                side_effect=fail_second_batch,
            ),
            self.assertRaisesMessage(RuntimeError, "Interrupted collection"),
        ):
            collect_project_metrics(date.isoformat())
        self.assertEqual(sizes, [2, 2])
        completed = list(
            Metric.objects.filter(scope=Metric.SCOPE_PROJECT, date=date).values_list(
                "pk", "changes", "data"
            )
        )
        self.assertEqual(len(completed), 2)
        with patch("weblate.metrics.tasks.BATCH_SIZE", 2):
            collect_project_metrics(date.isoformat())
        self.assertEqual(
            Metric.objects.filter(scope=Metric.SCOPE_PROJECT, date=date).count(), 4
        )
        for pk, changes, data in completed:
            metric = Metric.objects.get(pk=pk)
            self.assertEqual((metric.changes, metric.data), (changes, data))

    def test_language_pair_batches(self) -> None:
        """Even one parent can span multiple independent language batches."""
        from weblate.metrics.aggregation import language_pairs  # ruff: ignore[import-outside-top-level]
        from weblate.metrics.collection import collect_languages  # ruff: ignore[import-outside-top-level]

        category = Category.objects.create(
            project=self.project, name="Language batches", slug="language-batches"
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        for scope, parent, wrappers in (
            (
                "project",
                self.project,
                [
                    ProjectLanguage(self.project, lang)
                    for lang in self.project.languages
                ],
            ),
            (
                "category",
                category,
                [CategoryLanguage(category, lang) for lang in category.languages],
            ),
        ):
            with self.subTest(scope=scope):
                pairs = list(language_pairs(scope, [parent.pk], "default"))
                self.assertGreater(len(pairs), 1)
                self.warm_metric_stats(wrappers)
                with (
                    patch("weblate.metrics.collection.BATCH_SIZE", 1),
                    patch.object(
                        Metric.objects, "store_batch", wraps=Metric.objects.store_batch
                    ) as store,
                ):
                    collect_languages(
                        Metric.objects, [parent], scope, timezone.now().date()
                    )
                self.assertEqual(
                    [len(batch.args[0]) for batch in store.call_args_list],
                    [1] * len(pairs),
                )

    def warm_metric_stats(self, objects: list) -> None:
        for obj in objects:
            data = dict.fromkeys(SOURCE_KEYS, 0)
            obj.stats.set_data(data)
            cache.set(obj.stats.cache_key, data)
            self.addCleanup(cache.delete, obj.stats.cache_key)

    def test_batch_history_scopes(self) -> None:
        """Stored scope references and membership scopes retain their meanings."""
        from weblate.metrics.aggregation import history  # ruff: ignore[import-outside-top-level]

        Change.objects.all().delete()
        collection_date = timezone.now().date() - timedelta(days=5)
        start, end = dt_as_day_range(collection_date - timedelta(days=1))
        workspace = Workspace.objects.create(name="History metrics")
        category = Category.objects.create(
            project=self.project, name="History metrics", slug="history-metrics"
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        clist = ComponentList.objects.create(
            name="History metrics", slug="history-metrics"
        )
        clist.components.add(self.component)
        inactive = create_another_user("-metrics-inactive")
        bot = create_another_user("-metrics-bot-history")
        User.objects.filter(pk=inactive.pk).update(is_active=False)
        User.objects.filter(pk=bot.pk).update(is_bot=True)
        for user, timestamp in (
            (self.user, start),
            (self.user, end),
            (self.user, start - timedelta(microseconds=1)),
            (inactive, start),
            (bot, start),
            (self.user, start - timedelta(days=40)),
        ):
            change = self.translation.change_set.create(
                action=ActionEvents.CHANGE, user=user
            )
            Change.objects.filter(pk=change.pk).update(
                timestamp=timestamp, workspace=workspace
            )
        direct = Change.objects.create(
            action=ActionEvents.COMMENT, user=self.user, category=category
        )
        Change.objects.filter(pk=direct.pk).update(timestamp=start)
        scopes = (
            ("project", self.project, Change.objects.filter(project=self.project)),
            ("workspace", workspace, Change.objects.filter(workspace=workspace)),
            (
                "component",
                self.component,
                Change.objects.filter(component=self.component),
            ),
            (
                "translation",
                self.translation,
                Change.objects.filter(translation=self.translation),
            ),
            (
                "language",
                self.translation.language,
                Change.objects.filter(language=self.translation.language),
            ),
            ("category", category, Change.objects.for_category(category)),
            ("component_list", clist, Change.objects.filter(component=self.component)),
        )
        for scope, obj, queryset in scopes:
            with self.subTest(scope=scope):
                expected = get_change_metric_data(queryset, collection_date)
                with self.assertNumQueries(2):
                    actual = history(scope, [obj.pk], collection_date, "default")
                self.assertEqual(actual[obj.pk], expected)

    def test_batch_category_deduplicates_direct_and_component_history(self) -> None:
        from weblate.metrics.aggregation import history  # ruff: ignore[import-outside-top-level]

        Change.objects.all().delete()
        parent = Category.objects.create(
            project=self.project, name="Batch parent", slug="batch-parent"
        )
        child = Category.objects.create(
            project=self.project,
            category=parent,
            name="Batch child",
            slug="batch-child",
        )
        self.component.category = child
        self.component.save(update_fields=["category"])
        ComponentLink.objects.create(
            component=self.component, project=self.project, category=parent
        )
        change = self.translation.change_set.create(
            action=ActionEvents.CHANGE, user=self.user
        )
        Change.objects.filter(pk=change.pk).update(
            category=parent, timestamp=timezone.now() - timedelta(days=1)
        )
        collection_date = timezone.now().date()
        with self.assertNumQueries(2):
            data = history(
                "category", [parent.pk, child.pk], collection_date, "default"
            )
        self.assertEqual(
            data[parent.pk], {"changes": 1, "contributors": 1, "contributors_total": 1}
        )
        self.assertEqual(data[child.pk], data[parent.pk])

    def test_batch_collect_queries(self) -> None:
        """Warm collection costs depend on batches rather than object count."""
        collection_date = timezone.now().date() - timedelta(days=5)
        projects = [
            self.project,
            Project.objects.create(name="Batch empty", slug="batch-empty"),
        ]
        categories = [
            Category.objects.create(
                project=self.project, name=f"Batch {index}", slug=f"batch-{index}"
            )
            for index in range(2)
        ]
        lists = [
            ComponentList.objects.create(name=f"Batch {index}", slug=f"batch-{index}")
            for index in range(2)
        ]
        for clist in lists:
            clist.components.add(self.component)
        workspaces = [
            Workspace.objects.create(name=f"Batch {index}") for index in range(2)
        ]
        language = self.translation.language
        other_language = self.component.source_language
        other_component = self.create_po(name="Batch second")
        groups = (
            projects,
            categories,
            lists,
            workspaces,
            [self.component, other_component],
            list(self.component.translation_set.order_by("pk")[:2]),
            [language, other_language],
        )
        for objects in groups:
            self.warm_metric_stats(objects)
            if isinstance(objects[0], Project):
                self.warm_metric_stats(
                    [
                        ProjectLanguage(self.project, lang)
                        for lang in self.project.languages
                    ]
                )
            counts = []
            for count in (1, 2):
                Metric.objects.filter(date=collection_date).delete()
                with CaptureQueriesContext(connection) as queries:
                    Metric.objects.collect_batch(objects[:count], collection_date)
                counts.append(len(queries))
            with self.subTest(model=type(objects[0]).__name__):
                self.assertEqual(counts[0], counts[1])

    def test_batch_auxiliary_counters(self) -> None:
        from weblate.memory.models import Memory, MemoryScope  # ruff: ignore[import-outside-top-level]
        from weblate.metrics.aggregation import counters  # ruff: ignore[import-outside-top-level]
        from weblate.screenshots.models import Screenshot  # ruff: ignore[import-outside-top-level]

        workspace = Workspace.objects.create(name="Counter workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=workspace)
        memory = Memory.objects.create(
            source_language=self.component.source_language,
            target_language=self.translation.language,
            source="Counter source",
            target="Counter target",
            origin="Metrics test",
        )
        for scope in (MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE):
            MemoryScope.objects.create(memory=memory, project=self.project, scope=scope)
        for source in (None, self.project):
            MemoryScope.objects.create(
                memory=memory,
                workspace=workspace,
                source_project=source,
                scope=MemoryScope.SCOPE_WORKSPACE,
            )
        Screenshot.objects.create(translation=self.translation, name="Metric counter")
        self.user.profile.languages.add(self.translation.language)
        project = counters("project", [self.project.pk], "default")[self.project.pk]
        self.assertEqual(project["memory"], 1)
        self.assertEqual(project["components"], 1)
        self.assertEqual(
            project["translations"], self.component.translation_set.count()
        )
        self.assertEqual(project["screenshots"], 1)
        workspace_data = counters("workspace", [workspace.pk], "default")[workspace.pk]
        self.assertEqual(workspace_data, {**project, "projects": 1})
        language = self.translation.language
        language_data = counters("language", [language.pk], "default")[language.pk]
        self.assertEqual(language_data["users"], language.profile_set.count())

    def test_batch_machinery_accounting(self) -> None:
        date = timezone.now().date() - timedelta(days=5)
        self.warm_metric_stats([self.project])
        self.warm_metric_stats(
            [ProjectLanguage(self.project, lang) for lang in self.project.languages]
        )
        keys = {
            f"machinery-accounting:{kind}:{self.project.pk}": value
            for kind, value in (("internal", 13), ("external", 17))
        }
        cache.set_many(keys)
        Metric.objects.collect_batch([self.project], date)
        metric = Metric.objects.get(
            scope=Metric.SCOPE_PROJECT, relation=self.project.pk, date=date
        )
        self.assertEqual(metric.dict_data["machinery:internal"], 13)
        self.assertEqual(metric.dict_data["machinery:external"], 17)
        self.assertFalse(cache.get_many(keys))
        Metric.objects.collect_batch([self.project], date)
        metric.refresh_from_db()
        self.assertEqual(metric.dict_data["machinery:internal"], 13)

    def test_batch_language_pairs_and_counters(self) -> None:
        target = Project.objects.create(name="Batch linked", slug="batch-linked")
        category = Category.objects.create(
            project=target, name="Batch linked", slug="batch-linked"
        )
        ComponentLink.objects.create(
            component=self.component, project=target, category=category
        )
        dates = [timezone.now().date() - timedelta(days=offset) for offset in (5, 6)]
        for obj, language_scope, parent_scope in (
            (
                target,
                Metric.SCOPE_PROJECT_LANGUAGE,
                Metric.SCOPE_PROJECT,
            ),
            (
                category,
                Metric.SCOPE_CATEGORY_LANGUAGE,
                Metric.SCOPE_CATEGORY,
            ),
        ):
            self.warm_metric_stats([obj])
            languages = list(obj.languages)
            self.warm_metric_stats(
                [
                    (
                        ProjectLanguage(obj, language)
                        if isinstance(obj, Project)
                        else CategoryLanguage(obj, language)
                    )
                    for language in languages
                ]
            )
            for date in dates:
                Metric.objects.collect_batch([obj], date)
                rows = Metric.objects.filter(
                    scope=language_scope, relation=obj.pk, date=date
                )
                self.assertEqual(
                    set(rows.values_list("secondary", flat=True)),
                    {lang.pk for lang in languages},
                )
                parent = Metric.objects.get(
                    scope=parent_scope, relation=obj.pk, date=date
                )
                # Project counts include owned components only; category counts include links.
                self.assertEqual(
                    parent.dict_data["components"], int(isinstance(obj, Category))
                )

    def test_store_batch_preserves_composite_keys(self) -> None:
        date = timezone.now().date() - timedelta(days=5)
        metrics = []
        for index, data in enumerate((None, [], [42])):
            Metric.objects.create(
                scope=Metric.SCOPE_PROJECT_LANGUAGE,
                relation=self.project.pk,
                secondary=index,
                date=date,
                changes=17,
                data=data,
            )
            metrics.append(
                Metric(
                    scope=Metric.SCOPE_PROJECT_LANGUAGE,
                    relation=self.project.pk,
                    secondary=index,
                    date=date,
                    changes=99,
                    data=[23],
                )
            )
        untouched = Metric.objects.create(
            scope=Metric.SCOPE_PROJECT_LANGUAGE,
            relation=self.project.pk,
            secondary=9,
            date=date,
            changes=11,
        )
        for _ in range(2):
            Metric.objects.store_batch(metrics)
            rows = (
                Metric.objects.filter(
                    scope=Metric.SCOPE_PROJECT_LANGUAGE,
                    relation=self.project.pk,
                    date=date,
                )
                .exclude(pk=untouched.pk)
                .order_by("secondary")
            )
            self.assertEqual(
                list(rows.values_list("changes", "data")),
                [(17, [23]), (17, [23]), (17, [42])],
            )
        untouched.refresh_from_db()
        self.assertIsNone(untouched.data)

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

    def test_collect_category_component_counts(self) -> None:
        other = Project.objects.create(name="Metrics target", slug="metrics-target")
        parent = Category.objects.create(project=other, name="Parent", slug="parent")
        child = Category.objects.create(
            project=other, category=parent, name="Child", slug="child"
        )
        grandchild = Category.objects.create(
            project=other, category=child, name="Grandchild", slug="grandchild"
        )
        owned = self.create_po(project=other, name="Owned", category=child)
        expected_translations = (
            owned.translation_set.count() + self.component.translation_set.count()
        )
        link = ComponentLink.objects.create(
            component=self.component, project=other, category=grandchild
        )
        for placement in (parent, child, grandchild):
            link.category = placement
            link.save(update_fields=["category"])
            category = Category.objects.get(pk=parent.pk)
            with self.subTest(placement=placement):
                metric = Metric.objects.collect_category(category)
                self.assertEqual(metric.dict_data["components"], 2)
                self.assertEqual(
                    metric.dict_data["translations"], expected_translations
                )

        empty = Category.objects.create(project=other, name="Empty", slug="empty")
        metric = Metric.objects.collect_category(empty)
        self.assertEqual(metric.dict_data["components"], 0)
        self.assertEqual(metric.dict_data["translations"], 0)

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
