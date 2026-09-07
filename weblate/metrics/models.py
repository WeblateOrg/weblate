# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime
from itertools import zip_longest
from typing import TYPE_CHECKING, TypedDict, cast

from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.memory.models import Memory, MemoryScope
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Category,
    Component,
    ComponentLink,
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
    prefetch_stats,
)
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
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


def get_change_metric_data(
    changes: ChangeQuerySet, date: datetime.date
) -> ChangeMetricData:
    """Calculate change metrics using two aggregate queries."""
    active_user = Q(user__is_active=True, user__is_bot=False)
    recent = changes.since_day(date - datetime.timedelta(days=30)).aggregate(
        changes=Count(
            "id",
            filter=Q(
                timestamp__range=dt_as_day_range(date - datetime.timedelta(days=1))
            ),
        ),
        contributors=Count("user", filter=active_user, distinct=True),
    )
    total = changes.aggregate(
        contributors_total=Count("user", filter=active_user, distinct=True)
    )
    return {
        "changes": recent["changes"],
        "contributors": recent["contributors"],
        "contributors_total": total["contributors_total"],
    }


def get_language_change_metric_data(
    changes: ChangeQuerySet, date: datetime.date
) -> dict[int, ChangeMetricData]:
    """Calculate change metrics grouped by translation language."""
    active_user = Q(user__is_active=True, user__is_bot=False)
    language_key = "translation__language_id"
    result: dict[int, ChangeMetricData] = {}
    for row in (
        changes.since_day(date - datetime.timedelta(days=30))
        .values(language_key)
        .annotate(
            changes=Count(
                "id",
                filter=Q(
                    timestamp__range=dt_as_day_range(date - datetime.timedelta(days=1))
                ),
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
        yesterday = today - datetime.timedelta(days=1)

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
        date: datetime.date | None = None,
    ):
        if stats is not None:
            for key in keys:
                data[key] = getattr(stats, key)
        if date is None:
            date = timezone.now().date()

        # Prepare data for database
        db_data = None
        changes = data.pop("changes")
        if data:
            db_data = [data.pop(name, 0) for name in METRIC_ORDER]
            if data:
                msg = f"Unsupported data: {data}"
                raise ValueError(msg)

        metric, created = self.get_or_create(
            scope=scope,
            relation=relation,
            secondary=secondary,
            date=date,
            defaults={
                "changes": changes,
                "data": db_data,
            },
        )
        if not created and not metric.data and db_data:
            metric.data = db_data
            metric.save(update_fields=["data"])
        return metric

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

        count = changes.filter_by_day(date - datetime.timedelta(days=1)).count()
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
    def collect_global(self, date: datetime.date | None = None):
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
        date: datetime.date | None = None,
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
        date: datetime.date | None = None,
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

    @transaction.atomic
    def collect_category(self, category: Category, date: datetime.date | None = None):
        date = date or timezone.now().date()
        changes = Change.objects.for_category(category)
        language_change_data = get_language_change_metric_data(changes, date)
        languages = prefetch_stats(
            [CategoryLanguage(category, language) for language in category.languages]
        )
        for category_language in languages:
            self.collect_category_language(
                category_language,
                date,
                language_change_data.get(
                    category_language.language.pk,
                    {"changes": 0, "contributors": 0, "contributors_total": 0},
                ),
            )
        category_filter = (
            Q(category=category)
            | Q(category__category=category)
            | Q(category__category__category=category)
        )
        shared_component_ids = ComponentLink.objects.filter(
            Q(category=category)
            | Q(category__category=category)
            | Q(category__category__category=category)
        ).values_list("component_id", flat=True)
        components = Component.objects.filter(
            category_filter | Q(pk__in=shared_component_ids)
        ).distinct()
        data = {
            "components": components.count(),
            "translations": Translation.objects.filter(
                component__in=components
            ).count(),
            **get_change_metric_data(changes, date),
        }

        return self.create_metrics(
            data,
            category.stats,
            SOURCE_KEYS,
            Metric.SCOPE_CATEGORY,
            category.pk,
            date=date,
        )

    @transaction.atomic
    def collect_project(self, project: Project, date: datetime.date | None = None):
        date = date or timezone.now().date()
        changes = project.change_set.all()
        language_change_data = get_language_change_metric_data(changes, date)
        languages = prefetch_stats(
            [ProjectLanguage(project, language) for language in project.languages]
        )
        for project_language in languages:
            self.collect_project_language(
                project_language,
                date,
                language_change_data.get(
                    project_language.language.pk,
                    {"changes": 0, "contributors": 0, "contributors_total": 0},
                ),
            )
        project_scope = MemoryScope.objects.filter(
            memory_id=OuterRef("pk"),
            project=project,
            scope__in=(MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE),
        )
        data = {
            "components": project.component_set.count(),
            "translations": Translation.objects.filter(
                component__project=project
            ).count(),
            "memory": Memory.objects.alias(has_project_scope=Exists(project_scope))
            .filter(has_project_scope=True)
            .count(),
            "screenshots": Screenshot.objects.filter(
                translation__component__project=project
            ).count(),
            **get_change_metric_data(changes, date),
        }
        keys = [
            f"machinery-accounting:internal:{project.id}",
            f"machinery-accounting:external:{project.id}",
        ]
        for key, value in cache.get_many(keys).items():
            if ":internal:" in key:
                data["machinery:internal"] = value
            else:
                data["machinery:external"] = value
        cache.delete_many(keys)

        return self.create_metrics(
            data,
            project.stats,
            SOURCE_KEYS,
            Metric.SCOPE_PROJECT,
            project.pk,
            date=date,
        )

    @transaction.atomic
    def collect_workspace(
        self, workspace: Workspace, date: datetime.date | None = None
    ):
        date = date or timezone.now().date()
        workspace_scope = MemoryScope.objects.filter(
            memory_id=OuterRef("pk"),
            workspace=workspace,
            scope=MemoryScope.SCOPE_WORKSPACE,
        )
        changes = workspace.change_set.all()
        data = {
            "projects": workspace.projects.count(),
            "components": Component.objects.filter(
                project__workspace=workspace
            ).count(),
            "translations": Translation.objects.filter(
                component__project__workspace=workspace
            ).count(),
            "memory": Memory.objects.alias(has_workspace_scope=Exists(workspace_scope))
            .filter(has_workspace_scope=True)
            .count(),
            "screenshots": Screenshot.objects.filter(
                translation__component__project__workspace=workspace
            ).count(),
            **get_change_metric_data(changes, date),
        }
        return self.create_metrics(
            data,
            workspace.stats,
            SOURCE_KEYS,
            Metric.SCOPE_WORKSPACE,
            workspace.metric_id,
            date=date,
        )

    @transaction.atomic
    def collect_component(
        self, component: Component, date: datetime.date | None = None
    ):
        date = date or timezone.now().date()
        changes = component.change_set.all()
        data = {
            "translations": component.translation_set.count(),
            "screenshots": Screenshot.objects.filter(
                translation__component=component
            ).count(),
            **get_change_metric_data(changes, date),
        }
        return self.create_metrics(
            data,
            component.stats,
            SOURCE_KEYS,
            Metric.SCOPE_COMPONENT,
            component.pk,
            date=date,
        )

    @transaction.atomic
    def collect_component_list(
        self, clist: ComponentList, date: datetime.date | None = None
    ):
        date = date or timezone.now().date()
        changes = Change.objects.filter(component__in=clist.components.all())
        data = dict(get_change_metric_data(changes, date))
        return self.create_metrics(
            data,
            clist.stats,
            SOURCE_KEYS,
            Metric.SCOPE_COMPONENT_LIST,
            clist.pk,
            date=date,
        )

    @transaction.atomic
    def collect_translation(
        self, translation: Translation, date: datetime.date | None = None
    ):
        date = date or timezone.now().date()
        changes = translation.change_set.all()
        data = {
            "screenshots": translation.screenshot_set.count(),
            **get_change_metric_data(changes, date),
        }
        return self.create_metrics(
            data,
            translation.stats,
            BASIC_KEYS,
            Metric.SCOPE_TRANSLATION,
            translation.pk,
            date=date,
        )

    @transaction.atomic
    def collect_user(self, user: User, date: datetime.date | None = None):
        date = date or timezone.now().date()
        data = user.change_set.filter_by_day(
            date - datetime.timedelta(days=1)
        ).aggregate(
            changes=Count("id"),
            comments=Count("id", filter=Q(action=ActionEvents.COMMENT)),
            suggestions=Count("id", filter=Q(action=ActionEvents.SUGGESTION)),
            translations=Count("id", filter=Q(action__in=Change.ACTIONS_CONTENT)),
            screenshots=Count(
                "id",
                filter=Q(
                    action__in=(
                        ActionEvents.SCREENSHOT_ADDED,
                        ActionEvents.SCREENSHOT_UPLOADED,
                    )
                ),
            ),
        )
        return self.create_metrics(
            data, None, set(), Metric.SCOPE_USER, user.pk, date=date
        )

    @transaction.atomic
    def collect_language(self, language: Language, date: datetime.date | None = None):
        date = date or timezone.now().date()
        changes = language.change_set.all()
        data = {
            "users": language.profile_set.count(),
            **get_change_metric_data(changes, date),
        }
        return self.create_metrics(
            data,
            language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_LANGUAGE,
            language.pk,
            date=date,
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
    date = models.DateField(default=datetime.date.today)
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
