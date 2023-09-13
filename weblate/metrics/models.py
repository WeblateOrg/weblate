# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime
from itertools import zip_longest

from django.core.cache import cache
from django.db import models
from django.db.models import Count, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.stats import (
    CategoryLanguage,
    GlobalStats,
    ProjectLanguage,
    prefetch_stats,
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
]


class MetricQuerySet(models.QuerySet):
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


class MetricManager(models.Manager):
    def create_metrics(
        self,
        data: dict,
        stats: dict | None,
        keys: set,
        scope: int,
        relation: int,
        secondary: int = 0,
        date=None,
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
                raise ValueError(f"Unsupported data: {data}")

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

    def initialize_metrics(self, scope: int, relation: int, secondary: int = 0):
        today = timezone.now().date()
        # 2 years + one day for leap years
        self.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    changes=0,
                    date=today - datetime.timedelta(days=day),
                )
                for day in range(2 * 365 + 1)
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
        if obj is None:
            changes = Change.objects.all()
        elif isinstance(
            obj,
            (
                Translation,
                Component,
                Project,
                User,
                Language,
                ProjectLanguage,
                CategoryLanguage,
            ),
        ):
            changes = obj.change_set.all()
        elif isinstance(obj, ComponentList):
            changes = Change.objects.filter(component__in=obj.components.all())
        elif isinstance(obj, Category):
            changes = Change.objects.for_category(obj)
        else:
            raise TypeError(f"Unsupported type for metrics: {obj!r}")

        count = changes.filter(
            timestamp__date=date - datetime.timedelta(days=1)
        ).count()
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
        raise ValueError(f"Unsupported type for metrics: {obj!r}")

    def collect_global(self):
        stats = GlobalStats()
        data = {
            "projects": Project.objects.count(),
            "components": Component.objects.count(),
            "translations": Translation.objects.count(),
            "memory": Memory.objects.count(),
            "screenshots": Screenshot.objects.count(),
            "changes": Change.objects.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": Change.objects.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
            "users": User.objects.count(),
        }
        return self.create_metrics(data, stats, SOURCE_KEYS, Metric.SCOPE_GLOBAL, 0)

    def collect_project_language(self, project_language: ProjectLanguage):
        project = project_language.project
        changes = project.change_set.filter(
            translation__language=project_language.language
        )

        data = {
            "changes": changes.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1),
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=timezone.now().date()
                - datetime.timedelta(days=30),
            )
            .values("user")
            .distinct()
            .count(),
        }

        return self.create_metrics(
            data,
            project_language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_PROJECT_LANGUAGE,
            project.pk,
            project_language.language.pk,
        )

    def collect_category_language(self, category_language: CategoryLanguage):
        category = category_language.category
        changes = category.project.change_set.for_category(category).filter(
            translation__language=category_language.language
        )

        data = {
            "changes": changes.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1),
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=timezone.now().date()
                - datetime.timedelta(days=30),
            )
            .values("user")
            .distinct()
            .count(),
        }

        return self.create_metrics(
            data,
            category_language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_CATEGORY_LANGUAGE,
            category.project.pk,
            category_language.language.pk,
        )

    def collect_category(self, category: Category):
        languages = prefetch_stats(
            [CategoryLanguage(category, language) for language in category.languages]
        )
        for category_language in languages:
            self.collect_category_language(category_language)
        changes = Change.objects.for_category(category)
        data = {
            "components": category.component_set.count(),
            "translations": Translation.objects.filter(
                component__category=category
            ).count(),
            "changes": changes.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }

        return self.create_metrics(
            data, category.stats, SOURCE_KEYS, Metric.SCOPE_CATEGORY, category.pk
        )

    def collect_project(self, project: Project):
        languages = prefetch_stats(
            [ProjectLanguage(project, language) for language in project.languages]
        )
        for project_language in languages:
            self.collect_project_language(project_language)
        data = {
            "components": project.component_set.count(),
            "translations": Translation.objects.filter(
                component__project=project
            ).count(),
            "memory": project.memory_set.count(),
            "screenshots": Screenshot.objects.filter(
                translation__component__project=project
            ).count(),
            "changes": project.change_set.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": project.change_set.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
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
            data, project.stats, SOURCE_KEYS, Metric.SCOPE_PROJECT, project.pk
        )

    def collect_component(self, component: Component):
        data = {
            "translations": component.translation_set.count(),
            "screenshots": Screenshot.objects.filter(
                translation__component=component
            ).count(),
            "changes": component.change_set.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": component.change_set.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        return self.create_metrics(
            data, component.stats, SOURCE_KEYS, Metric.SCOPE_COMPONENT, component.pk
        )

    def collect_component_list(self, clist: ComponentList):
        changes = Change.objects.filter(component__in=clist.components.all())
        data = {
            "changes": changes.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        return self.create_metrics(
            data,
            clist.stats,
            SOURCE_KEYS,
            Metric.SCOPE_COMPONENT_LIST,
            clist.pk,
        )

    def collect_translation(self, translation: Translation):
        data = {
            "screenshots": translation.screenshot_set.count(),
            "changes": translation.change_set.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
            ).count(),
            "contributors": translation.change_set.filter(
                timestamp__date__gte=timezone.now().date() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        return self.create_metrics(
            data,
            translation.stats,
            BASIC_KEYS,
            Metric.SCOPE_TRANSLATION,
            translation.pk,
        )

    def collect_user(self, user: User):
        data = user.change_set.filter(
            timestamp__date=timezone.now().date() - datetime.timedelta(days=1)
        ).aggregate(
            changes=Count("id"),
            comments=Count("id", filter=Q(action=Change.ACTION_COMMENT)),
            suggestions=Count("id", filter=Q(action=Change.ACTION_SUGGESTION)),
            translations=Count("id", filter=Q(action__in=Change.ACTIONS_CONTENT)),
            screenshots=Count(
                "id",
                filter=Q(
                    action__in=(
                        Change.ACTION_SCREENSHOT_ADDED,
                        Change.ACTION_SCREENSHOT_UPLOADED,
                    )
                ),
            ),
        )
        return self.create_metrics(data, None, None, Metric.SCOPE_USER, user.pk)

    def collect_language(self, language: Language):
        changes = language.change_set.all()
        data = {
            "changes": changes.filter(
                timestamp__date=timezone.now().date() - datetime.timedelta(days=1),
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=timezone.now().date()
                - datetime.timedelta(days=30),
            )
            .values("user")
            .distinct()
            .count(),
            "users": language.profile_set.count(),
        }
        return self.create_metrics(
            data,
            language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_LANGUAGE,
            language.pk,
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

    id = models.BigAutoField(primary_key=True)  # noqa: A003
    date = models.DateField(default=datetime.date.today)
    scope = models.SmallIntegerField()
    relation = models.IntegerField()
    secondary = models.IntegerField(default=0)
    changes = models.IntegerField()
    data = models.JSONField(null=True)

    objects = MetricManager.from_queryset(MetricQuerySet)()

    class Meta:
        unique_together = (("scope", "relation", "secondary", "date"),)
        verbose_name = "Metric"
        verbose_name_plural = "Metrics"

    def __str__(self):
        return f"<{self.scope}.{self.relation}>:{self.date}:{self.changes} {self.data}"

    @cached_property
    def dict_data(self) -> dict:
        return dict(zip_longest(METRIC_ORDER, self.data or [], fillvalue=0))

    def __getitem__(self, item: str):
        return self.dict_data[item]

    def get(self, item: str, default=None):
        return self.dict_data.get(item, default)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def create_metrics_project(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_PROJECT, relation=instance.pk
        )


@receiver(post_save, sender=Category)
@disable_for_loaddata
def create_metrics_category(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_CATEGORY, relation=instance.pk
        )


@receiver(post_save, sender=Component)
@disable_for_loaddata
def create_metrics_component(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_COMPONENT, relation=instance.pk
        )


@receiver(post_save, sender=Translation)
@disable_for_loaddata
def create_metrics_translation(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_TRANSLATION, relation=instance.pk
        )


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_metrics_user(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(scope=Metric.SCOPE_USER, relation=instance.pk)


@receiver(post_delete, sender=Category)
@disable_for_loaddata
def delete_metrics_category(sender, instance, **kwargs):
    Metric.objects.filter(
        scope__in=(Metric.SCOPE_CATEGORY_LANGUAGE, Metric.SCOPE_CATEGORY),
        relation=instance.pk,
    ).delete()


@receiver(post_delete, sender=Project)
@disable_for_loaddata
def delete_metrics_project(sender, instance, **kwargs):
    Metric.objects.filter(
        scope__in=(Metric.SCOPE_PROJECT_LANGUAGE, Metric.SCOPE_PROJECT),
        relation=instance.pk,
    ).delete()


@receiver(post_delete, sender=Component)
@disable_for_loaddata
def delete_metrics_component(sender, instance, **kwargs):
    Metric.objects.filter(scope=Metric.SCOPE_COMPONENT, relation=instance.pk).delete()


@receiver(post_delete, sender=ComponentList)
@disable_for_loaddata
def delete_metrics_component_list(sender, instance, **kwargs):
    Metric.objects.filter(
        scope=Metric.SCOPE_COMPONENT_LIST, relation=instance.pk
    ).delete()


@receiver(post_delete, sender=Translation)
@disable_for_loaddata
def delete_metrics_translation(sender, instance, **kwargs):
    Metric.objects.filter(scope=Metric.SCOPE_TRANSLATION, relation=instance.pk).delete()


@receiver(post_delete, sender=User)
@disable_for_loaddata
def delete_metrics_user(sender, instance, **kwargs):
    Metric.objects.filter(scope=Metric.SCOPE_USER, relation=instance.pk).delete()


@receiver(post_delete, sender=Language)
@disable_for_loaddata
def delete_metrics_language(sender, instance, **kwargs):
    Metric.objects.filter(scope=Metric.SCOPE_LANGUAGE, relation=instance.pk).delete()
