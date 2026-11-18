# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime as dt
from itertools import zip_longest
from typing import TYPE_CHECKING, TypedDict, cast

from django.db import models, transaction
from django.db.models import Count, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.trans.models.change import Change, dt_as_day_range
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.stats import (
    CategoryLanguage,
    GlobalStats,
    ProjectLanguage,
)
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from weblate.metrics.collection import MetricObject
    from weblate.trans.models.change import ChangeQuerySet
    from weblate.utils.stats import (
        BaseStats,
    )

BASIC_KEYS = {
    "all",
    "all_words",
    "translated",
    "translated_words",
    "approved",
    "approved_words",
    "allchecks",
    "allchecks_words",
    "dismissed_checks",
    "dismissed_checks_words",
    "suggestions",
    "suggestions_words",
    "comments",
    "comments_words",
    "languages",
}
SOURCE_KEYS = BASIC_KEYS | {
    "source_strings",
    "source_words",
}

METRIC_ORDER = [
    "all",
    "all_words",
    "translated",
    "translated_words",
    "approved",
    "approved_words",
    "allchecks",
    "allchecks_words",
    "dismissed_checks",
    "dismissed_checks_words",
    "suggestions",
    "suggestions_words",
    "comments",
    "comments_words",
    "languages",
    "source_strings",
    "source_words",
    "changes",
    "memory",
    "users",
    "contributors",
    "projects",
    "screenshots",
    "components",
    "translations",
    "machinery:internal",
    "machinery:external",
    "public_projects",
    "contributors_total",
]


class ChangeMetricData(TypedDict):
    changes: int
    contributors: int
    contributors_total: int


def get_user_change_metric_expressions() -> dict[str, Count]:
    return {
        "changes": Count("id"),
        "comments": Count("id", filter=Q(action=ActionEvents.COMMENT)),
        "suggestions": Count("id", filter=Q(action=ActionEvents.SUGGESTION)),
        "translations": Count("id", filter=Q(action__in=Change.ACTIONS_CONTENT)),
        "screenshots": Count(
            "id",
            filter=Q(
                action__in=(
                    ActionEvents.SCREENSHOT_ADDED,
                    ActionEvents.SCREENSHOT_UPLOADED,
                )
            ),
        ),
    }


def serialize_metric_data(data: dict) -> tuple[int, list[int] | None]:
    """Extract the change count and serialize the remaining metric counters."""
    changes = data.pop("changes")
    db_data = None
    if data:
        db_data = [data.pop(name, 0) for name in METRIC_ORDER]
        if data:
            msg = f"Unsupported data: {data}"
            raise ValueError(msg)
    return changes, db_data


def get_change_metric_data(changes: ChangeQuerySet, date: dt.date) -> ChangeMetricData:
    """Calculate change metrics using two aggregate queries."""
    active_user = Q(user__is_active=True, user__is_bot=False)
    recent = changes.since_day(date - dt.timedelta(days=30)).aggregate(
        changes=Count(
            "id",
            filter=Q(timestamp__range=dt_as_day_range(date - dt.timedelta(days=1))),
        ),
        contributors=Count("user", filter=active_user, distinct=True),
    )
    total = changes.filter(active_user).aggregate(
        contributors_total=Count("user", distinct=True)
    )
    return {
        "changes": recent["changes"],
        "contributors": recent["contributors"],
        "contributors_total": total["contributors_total"],
    }


def get_language_change_metric_data(
    changes: ChangeQuerySet, date: dt.date
) -> dict[int, ChangeMetricData]:
    """Calculate change metrics grouped by translation language."""
    active_user = Q(user__is_active=True, user__is_bot=False)
    language_key = "translation__language_id"
    result: dict[int, ChangeMetricData] = {}
    for row in (
        changes.since_day(date - dt.timedelta(days=30))
        .values(language_key)
        .annotate(
            changes=Count(
                "id",
                filter=Q(timestamp__range=dt_as_day_range(date - dt.timedelta(days=1))),
            ),
            contributors=Count("user", filter=active_user, distinct=True),
        )
    ):
        language_id = row[language_key]
        if language_id is not None:
            result[language_id] = {
                "changes": row["changes"],
                "contributors": row["contributors"],
                "contributors_total": 0,
            }
    for row in (
        changes.filter(active_user)
        .values(language_key)
        .annotate(contributors_total=Count("user", distinct=True))
    ):
        language_id = row[language_key]
        if language_id is not None:
            result.setdefault(
                language_id,
                {"changes": 0, "contributors": 0, "contributors_total": 0},
            )["contributors_total"] = row["contributors_total"]
    return result


class MetricQuerySet(models.QuerySet["Metric", "Metric"]):
    def filter_metric(
        self, scope: int, relation: int, secondary: int = 0
    ) -> MetricQuerySet:
        # Include secondary in the query as it is part of unique index
        # and makes subsequent date filtering more effective.
        return self.filter(scope=scope, relation=relation, secondary=secondary)

    def get_current_metric(
        self, obj, scope: int, relation: int, secondary: int = 0
    ) -> Metric:
        today = timezone.now().date()
        yesterday = today - dt.timedelta(days=1)

        base = self.filter_metric(scope, relation, secondary)

        # Get metrics
        try:
            metric = base.get(date=today)
        except Metric.DoesNotExist:
            # Fallback to day before in case they are not yet calculated
            try:
                metric = base.get(date=yesterday)
            except Metric.DoesNotExist:
                metric = Metric()

        # Trigger collection in case no data is present or when only
        # changes are counted - when there is a single key.
        if metric.data is None:
            metric = Metric.objects.collect_auto(obj)

        return metric


class MetricManager(models.Manager["Metric"]):
    def create_metrics(
        self,
        data: dict,
        stats: BaseStats | None,
        keys: set,
        scope: int,
        relation: int,
        secondary: int = 0,
        date: dt.date | None = None,
    ):
        if stats is not None:
            for key in keys:
                data[key] = getattr(stats, key)
        if date is None:
            date = timezone.now().date()

        # Prepare data for database
        changes, db_data = serialize_metric_data(data)

        self.store_batch(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    date=date,
                    changes=changes,
                    data=db_data,
                )
            ]
        )
        return self.get(scope=scope, relation=relation, secondary=secondary, date=date)

    def initialize_metrics(self, scope: int, relation: int, secondary: int = 0) -> None:
        today = timezone.now().date()
        self.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    changes=0,
                    date=today,
                )
            ],
            ignore_conflicts=True,
        )

    def calculate_changes(
        self, date, obj, scope: int, relation: int, secondary: int = 0
    ):
        """
        Calculate changes for given scope and date.

        This is used to fill in blanks in a history.
        """
        changes: ChangeQuerySet
        if obj is None:
            changes = Change.objects.all()
        elif isinstance(
            obj,
            Translation
            | Component
            | Project
            | User
            | Language
            | ProjectLanguage
            | CategoryLanguage
            | Workspace,
        ):
            changes = cast("ChangeQuerySet", obj.change_set.all())  # type: ignore[misc]
        elif isinstance(obj, ComponentList):
            changes = Change.objects.filter(component__in=obj.components.all())
        elif isinstance(obj, Category):
            changes = Change.objects.for_category(obj)
        else:
            msg = f"Unsupported type for metrics: {obj!r}"
            raise TypeError(msg)

        count = changes.filter_by_day(date - dt.timedelta(days=1)).count()
        self.create_metrics(
            {"changes": count}, None, set(), scope, relation, secondary, date=date
        )
        return count

    def collect_auto(self, obj):
        if obj is None:
            return self.collect_global()
        if isinstance(obj, Translation):
            return self.collect_translation(obj)
        if isinstance(obj, Component):
            return self.collect_component(obj)
        if isinstance(obj, Project):
            return self.collect_project(obj)
        if isinstance(obj, Workspace):
            return self.collect_workspace(obj)
        if isinstance(obj, Category):
            return self.collect_category(obj)
        if isinstance(obj, ComponentList):
            return self.collect_component_list(obj)
        if isinstance(obj, ProjectLanguage):
            return self.collect_project_language(obj)
        if isinstance(obj, CategoryLanguage):
            return self.collect_category_language(obj)
        if isinstance(obj, Language):
            return self.collect_language(obj)
        msg = f"Unsupported type for metrics: {obj!r}"
        raise ValueError(msg)

    @transaction.atomic
    def collect_global(self, date: dt.date | None = None):
        date = date or timezone.now().date()
        stats = GlobalStats()
        changes = Change.objects.all()
        data = {
            "projects": Project.objects.count(),
            "public_projects": Project.objects.filter(
                access_control__in={Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED}
            ).count(),
            "components": Component.objects.count(),
            "translations": Translation.objects.count(),
            "memory": Memory.objects.count(),
            "screenshots": Screenshot.objects.count(),
            "users": User.objects.count(),
            **get_change_metric_data(changes, date),
        }
        return self.create_metrics(
            data, stats, SOURCE_KEYS, Metric.SCOPE_GLOBAL, 0, date=date
        )

    @transaction.atomic
    def collect_project_language(
        self,
        project_language: ProjectLanguage,
        date: dt.date | None = None,
        change_data: ChangeMetricData | None = None,
    ):
        date = date or timezone.now().date()
        project = project_language.project
        if change_data is None:
            changes = project.change_set.filter(
                translation__language=project_language.language
            )
            change_data = get_change_metric_data(changes, date)

        return self.create_metrics(
            dict(change_data),
            project_language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_PROJECT_LANGUAGE,
            project.pk,
            project_language.language.pk,
            date=date,
        )

    @transaction.atomic
    def collect_category_language(
        self,
        category_language: CategoryLanguage,
        date: dt.date | None = None,
        change_data: ChangeMetricData | None = None,
    ):
        date = date or timezone.now().date()
        category = category_language.category
        if change_data is None:
            changes = Change.objects.for_category(category).filter(
                translation__language=category_language.language
            )
            change_data = get_change_metric_data(changes, date)

        return self.create_metrics(
            dict(change_data),
            category_language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_CATEGORY_LANGUAGE,
            category.pk,
            category_language.language.pk,
            date=date,
        )

    def collect_category(self, category: Category, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([category], date)
        return self.get(
            scope=Metric.SCOPE_CATEGORY, relation=category.pk, secondary=0, date=date
        )

    def collect_project(self, project: Project, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([project], date)
        return self.get(
            scope=Metric.SCOPE_PROJECT, relation=project.pk, secondary=0, date=date
        )

    def collect_workspace(self, workspace: Workspace, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([workspace], date)
        return self.get(
            scope=Metric.SCOPE_WORKSPACE,
            relation=workspace.metric_id,
            secondary=0,
            date=date,
        )

    def collect_component(self, component: Component, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([component], date)
        return self.get(
            scope=Metric.SCOPE_COMPONENT, relation=component.pk, secondary=0, date=date
        )

    def collect_component_list(self, clist: ComponentList, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([clist], date)
        return self.get(
            scope=Metric.SCOPE_COMPONENT_LIST, relation=clist.pk, secondary=0, date=date
        )

    def collect_translation(
        self, translation: Translation, date: dt.date | None = None
    ):
        date = date or timezone.now().date()
        self.collect_batch([translation], date)
        return self.get(
            scope=Metric.SCOPE_TRANSLATION,
            relation=translation.pk,
            secondary=0,
            date=date,
        )

    def collect_users(self, user_ids: Collection[int], date: dt.date) -> None:
        """Collect a batch of user metrics without per-user queries."""
        if not user_ids:
            return
        user_ids = sorted(set(user_ids))
        expressions = get_user_change_metric_expressions()
        user_data = {}
        for row in (
            Change.objects.filter(user_id__in=user_ids)
            .filter_by_day(date - dt.timedelta(days=1))
            .order_by()
            .values("user_id")
            .annotate(**expressions)
        ):
            counters = dict(row)
            user_data[counters.pop("user_id")] = counters
        metrics = []
        for user_id in user_ids:
            changes, data = serialize_metric_data(
                user_data.get(user_id, dict.fromkeys(expressions, 0))
            )
            metrics.append(
                Metric(
                    scope=Metric.SCOPE_USER,
                    relation=user_id,
                    secondary=0,
                    date=date,
                    changes=changes,
                    data=data,
                )
            )

        self.store_batch(metrics)

    def collect_batch(self, objects: Sequence[MetricObject], date: dt.date) -> None:
        from weblate.metrics.collection import collect_batch  # ruff: ignore[import-outside-top-level]

        collect_batch(self, objects, date)

    def store_batch(self, metrics: list[Metric]) -> None:
        """Insert a bounded batch and fill incomplete rows without overwriting counters."""
        if not metrics:
            return
        from weblate.metrics.aggregation import BATCH_SIZE  # ruff: ignore[import-outside-top-level]

        if len(metrics) > BATCH_SIZE:
            msg = "Metric persistence batch exceeds its limit"
            raise ValueError(msg)
        metrics = sorted(
            metrics, key=lambda m: (m.scope, m.relation, m.secondary, m.date)
        )
        lookup = {(m.scope, m.relation, m.secondary, m.date): m.data for m in metrics}
        targets = Q()
        # Group exact pairs by their shared identity, avoiding large OR trees
        # both for many parents and for one parent with many languages.
        by_relation: dict[tuple[int, int, dt.date], list[int]] = {}
        by_secondary: dict[tuple[int, int, dt.date], list[int]] = {}
        for scope, relation, secondary, date in lookup:
            by_relation.setdefault((scope, relation, date), []).append(secondary)
            by_secondary.setdefault((scope, secondary, date), []).append(relation)
        if len(by_relation) < len(by_secondary):
            for (scope, relation, date), secondaries in by_relation.items():
                targets |= Q(
                    scope=scope, relation=relation, secondary__in=secondaries, date=date
                )
        else:
            for (scope, secondary, date), relations in by_secondary.items():
                targets |= Q(
                    scope=scope, relation__in=relations, secondary=secondary, date=date
                )
        with transaction.atomic(using=self.db):
            self.bulk_create(metrics, ignore_conflicts=True)
            incomplete = list(
                self.filter(targets)
                .filter(Q(data__isnull=True) | Q(data=[]))
                .order_by("scope", "relation", "secondary", "date")
                .select_for_update()
            )
            for metric in incomplete:
                metric.data = lookup[
                    metric.scope, metric.relation, metric.secondary, metric.date
                ]
            self.bulk_update([metric for metric in incomplete if metric.data], ["data"])

    def collect_language(self, language: Language, date: dt.date | None = None):
        date = date or timezone.now().date()
        self.collect_batch([language], date)
        return self.get(
            scope=Metric.SCOPE_LANGUAGE, relation=language.pk, secondary=0, date=date
        )


class Metric(models.Model):
    SCOPE_GLOBAL = 0
    SCOPE_PROJECT = 1
    SCOPE_COMPONENT = 2
    SCOPE_TRANSLATION = 3
    SCOPE_USER = 4
    SCOPE_COMPONENT_LIST = 5
    SCOPE_PROJECT_LANGUAGE = 6
    SCOPE_LANGUAGE = 7
    SCOPE_CATEGORY = 8
    SCOPE_CATEGORY_LANGUAGE = 9
    SCOPE_WORKSPACE = 10

    id = models.BigAutoField(primary_key=True)
    date = models.DateField(default=dt.date.today)
    scope = models.SmallIntegerField()
    relation = models.IntegerField()
    secondary = models.IntegerField(default=0)
    changes = models.IntegerField()
    data = models.JSONField(null=True)

    objects = MetricManager.from_queryset(MetricQuerySet)()

    class Meta:
        required_db_vendor = "postgresql"
        unique_together = (("scope", "relation", "secondary", "date"),)
        verbose_name = "Metric"
        verbose_name_plural = "Metrics"

    def __str__(self) -> str:
        return f"<{self.scope}.{self.relation}>:{self.date}:{self.changes} {self.data}"

    def __getitem__(self, item: str):
        return self.dict_data[item]

    @cached_property
    def dict_data(self) -> dict:
        return dict(zip_longest(METRIC_ORDER, self.data or [], fillvalue=0))

    def get(self, item: str, default=None):
        return self.dict_data.get(item, default)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def create_metrics_project(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_PROJECT, relation=instance.pk
        )


@receiver(post_save, sender=Workspace)
@disable_for_loaddata
def create_metrics_workspace(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_WORKSPACE, relation=instance.metric_id
        )


@receiver(post_save, sender=Category)
@disable_for_loaddata
def create_metrics_category(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_CATEGORY, relation=instance.pk
        )


@receiver(post_save, sender=Component)
@disable_for_loaddata
def create_metrics_component(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_COMPONENT, relation=instance.pk
        )


@receiver(post_save, sender=Translation)
@disable_for_loaddata
def create_metrics_translation(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_TRANSLATION, relation=instance.pk
        )


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_metrics_user(sender, instance, created=False, **kwargs) -> None:
    if created:
        Metric.objects.initialize_metrics(scope=Metric.SCOPE_USER, relation=instance.pk)


@receiver(post_delete, sender=Category)
@disable_for_loaddata
def delete_metrics_category(sender, instance, **kwargs) -> None:
    Metric.objects.filter(
        scope__in=(Metric.SCOPE_CATEGORY_LANGUAGE, Metric.SCOPE_CATEGORY),
        relation=instance.pk,
    ).delete()


@receiver(post_delete, sender=Workspace)
@disable_for_loaddata
def delete_metrics_workspace(sender, instance, **kwargs) -> None:
    Metric.objects.filter(
        scope=Metric.SCOPE_WORKSPACE, relation=instance.metric_id
    ).delete()


@receiver(post_delete, sender=Project)
@disable_for_loaddata
def delete_metrics_project(sender, instance, **kwargs) -> None:
    Metric.objects.filter(
        scope__in=(Metric.SCOPE_PROJECT_LANGUAGE, Metric.SCOPE_PROJECT),
        relation=instance.pk,
    ).delete()


@receiver(post_delete, sender=Component)
@disable_for_loaddata
def delete_metrics_component(sender, instance, **kwargs) -> None:
    Metric.objects.filter(scope=Metric.SCOPE_COMPONENT, relation=instance.pk).delete()


@receiver(post_delete, sender=ComponentList)
@disable_for_loaddata
def delete_metrics_component_list(sender, instance, **kwargs) -> None:
    Metric.objects.filter(
        scope=Metric.SCOPE_COMPONENT_LIST, relation=instance.pk
    ).delete()


@receiver(post_delete, sender=Translation)
@disable_for_loaddata
def delete_metrics_translation(sender, instance, **kwargs) -> None:
    Metric.objects.filter(scope=Metric.SCOPE_TRANSLATION, relation=instance.pk).delete()


@receiver(post_delete, sender=User)
@disable_for_loaddata
def delete_metrics_user(sender, instance, **kwargs) -> None:
    Metric.objects.filter(scope=Metric.SCOPE_USER, relation=instance.pk).delete()


@receiver(post_delete, sender=Language)
@disable_for_loaddata
def delete_metrics_language(sender, instance, **kwargs) -> None:
    Metric.objects.filter(scope=Metric.SCOPE_LANGUAGE, relation=instance.pk).delete()
