#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import datetime
from collections import defaultdict
from typing import Dict, Optional, Set

from django.core.cache import cache
from django.db import models
from django.db.models import Count, Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Change, Component, ComponentList, Project, Translation
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.stats import GlobalStats, ProjectLanguage, prefetch_stats

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

METRIC_ALL = 1
METRIC_ALL_WORDS = 2
METRIC_TRANSLATED = 3
METRIC_TRANSLATED_WORDS = 4
METRIC_APPROVED = 5
METRIC_APPROVED_WORDS = 6
METRIC_ALLCHECKS = 7
METRIC_ALLCHECKS_WORDS = 8
METRIC_DISMISSED_CHECKS = 9
METRIC_DISMISSED_CHECKS_WORDS = 10
METRIC_SUGGESTIONS = 11
METRIC_SUGGESTIONS_WORDS = 12
METRIC_COMMENTS = 13
METRIC_COMMENTS_WORDS = 14
METRIC_LANGUAGES = 15
METRIC_SOURCE_STRINGS = 16
METRIC_SOURCE_WORDS = 17
METRIC_CHANGES = 18
METRIC_MEMORY = 19
METRIC_USERS = 20
METRIC_CONTRIBUTORS = 21
METRIC_PROJECTS = 22
METRIC_SCREENSHOTS = 23
METRIC_COMPONENTS = 24
METRIC_TRANSLATIONS = 25
METRIC_MACHINERY_INTERNAL = 26
METRIC_MACHINERY_EXTERNAL = 27

METRIC_IDS = {
    "all": METRIC_ALL,
    "all_words": METRIC_ALL_WORDS,
    "translated": METRIC_TRANSLATED,
    "translated_words": METRIC_TRANSLATED_WORDS,
    "approved": METRIC_APPROVED,
    "approved_words": METRIC_APPROVED_WORDS,
    "allchecks": METRIC_ALLCHECKS,
    "allchecks_words": METRIC_ALLCHECKS_WORDS,
    "dismissed_checks": METRIC_DISMISSED_CHECKS,
    "dismissed_checks_words": METRIC_DISMISSED_CHECKS_WORDS,
    "suggestions": METRIC_SUGGESTIONS,
    "suggestions_words": METRIC_SUGGESTIONS_WORDS,
    "comments": METRIC_COMMENTS,
    "comments_words": METRIC_COMMENTS_WORDS,
    "languages": METRIC_LANGUAGES,
    "source_strings": METRIC_SOURCE_STRINGS,
    "source_words": METRIC_SOURCE_WORDS,
    "changes": METRIC_CHANGES,
    "memory": METRIC_MEMORY,
    "users": METRIC_USERS,
    "contributors": METRIC_CONTRIBUTORS,
    "projects": METRIC_PROJECTS,
    "screenshots": METRIC_SCREENSHOTS,
    "components": METRIC_COMPONENTS,
    "translations": METRIC_TRANSLATIONS,
    "machinery:internal": METRIC_MACHINERY_INTERNAL,
    "machinery:external": METRIC_MACHINERY_EXTERNAL,
}

METRIC_NAMES = {value: name for name, value in METRIC_IDS.items()}


def get_metric_names(values):
    """Convert numeric kind to human friendly names."""
    for kind, value in values:
        yield METRIC_NAMES[kind], value


class MetricQuerySet(models.QuerySet):
    def get_kwargs(
        self, kwargs: Dict, scope: int, relation: int, secondary: int = 0
    ) -> Dict:
        """Build the query params."""
        if "name" in kwargs:
            kwargs["kind"] = METRIC_IDS[kwargs["name"]]
            del kwargs["name"]
        kwargs["scope"] = scope
        kwargs["relation"] = relation
        if secondary:
            # If secondary is 0 it is not used for this metric
            kwargs["secondary"] = secondary
        return kwargs

    def get_current(self, obj, scope: int, relation: int, secondary: int = 0, **kwargs):
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)

        kwargs = self.get_kwargs(kwargs, scope, relation, secondary)

        # Get todays stats
        data = dict(
            get_metric_names(
                self.filter(
                    date=today,
                    **kwargs,
                ).values_list("kind", "value")
            )
        )
        if not data:
            # Fallback to yesterday in case they are not yet calculated
            data = dict(
                get_metric_names(
                    self.filter(
                        date=yesterday,
                        **kwargs,
                    ).values_list("kind", "value")
                )
            )

        # Trigger collection in case no data is present or when only
        # changes are counted - when there is a single key. The exception from
        # this is when name filtering is passed in the kwargs.
        if not data or (len(data.keys()) <= 1 and "kind" not in kwargs):
            data.update(Metric.objects.collect_auto(obj))
        return data

    def get_past(
        self, scope: int, relation: int, secondary: int = 0, delta: int = 30, **kwargs
    ):
        kwargs = self.get_kwargs(kwargs, scope, relation, secondary)
        return defaultdict(
            int,
            get_metric_names(
                self.filter(
                    date=datetime.date.today() - datetime.timedelta(days=delta),
                    **kwargs,
                ).values_list("kind", "value")
            ),
        )


class MetricsManager(models.Manager):
    def create_metrics(
        self,
        data: Dict,
        stats: Optional[Dict],
        keys: Set,
        scope: int,
        relation: int,
        secondary: int = 0,
        date=None,
    ):
        if stats is not None:
            for key in keys:
                data[key] = getattr(stats, key)
        if date is None:
            date = datetime.date.today()

        self.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    kind=METRIC_IDS[name],
                    value=value,
                    date=date,
                )
                for name, value in data.items()
            ],
            ignore_conflicts=True,
        )

    def initialize_metrics(self, scope: int, relation: int, secondary: int = 0):
        today = datetime.date.today()
        # 2 years + one day for leap years
        self.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    kind=METRIC_CHANGES,
                    value=0,
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
        elif isinstance(obj, Translation):
            changes = obj.change_set.all()
        elif isinstance(obj, Component):
            changes = obj.change_set.all()
        elif isinstance(obj, Project):
            changes = obj.change_set.all()
        elif isinstance(obj, ComponentList):
            changes = Change.objects.filter(component__in=obj.components.all())
        elif isinstance(obj, ProjectLanguage):
            changes = obj.project.change_set.filter(translation__language=obj.language)
        elif isinstance(obj, Language):
            changes = Change.objects.filter(translation__language=obj)
        elif isinstance(obj, User):
            changes = obj.change_set.all()
        else:
            raise ValueError(f"Unsupported type for metrics: {obj!r}")

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
        if isinstance(obj, ComponentList):
            return self.collect_component_list(obj)
        if isinstance(obj, ProjectLanguage):
            return self.collect_project_language(obj)
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
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
            ).count(),
            "contributors": Change.objects.filter(
                timestamp__date__gte=datetime.date.today() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
            "users": User.objects.count(),
        }
        self.create_metrics(data, stats, SOURCE_KEYS, Metric.SCOPE_GLOBAL, 0)
        return data

    def collect_project_language(self, project_language: ProjectLanguage):
        project = project_language.project
        changes = project.change_set.filter(
            translation__language=project_language.language
        )

        data = {
            "changes": changes.filter(
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1),
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=datetime.date.today()
                - datetime.timedelta(days=30),
            )
            .values("user")
            .distinct()
            .count(),
        }

        self.create_metrics(
            data,
            project_language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_PROJECT_LANGUAGE,
            project.pk,
            project_language.language.pk,
        )
        return data

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
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
            ).count(),
            "contributors": project.change_set.filter(
                timestamp__date__gte=datetime.date.today() - datetime.timedelta(days=30)
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

        self.create_metrics(
            data, project.stats, SOURCE_KEYS, Metric.SCOPE_PROJECT, project.pk
        )
        return data

    def collect_component(self, component: Component):
        data = {
            "translations": component.translation_set.count(),
            "screenshots": Screenshot.objects.filter(
                translation__component=component
            ).count(),
            "changes": component.change_set.filter(
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
            ).count(),
            "contributors": component.change_set.filter(
                timestamp__date__gte=datetime.date.today() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        self.create_metrics(
            data, component.stats, SOURCE_KEYS, Metric.SCOPE_COMPONENT, component.pk
        )
        return data

    def collect_component_list(self, clist: ComponentList):
        changes = Change.objects.filter(component__in=clist.components.all())
        data = {
            "changes": changes.filter(
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=datetime.date.today() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        self.create_metrics(
            data,
            clist.stats,
            SOURCE_KEYS,
            Metric.SCOPE_COMPONENT_LIST,
            clist.pk,
        )
        return data

    def collect_translation(self, translation: Translation):
        data = {
            "screenshots": translation.screenshot_set.count(),
            "changes": translation.change_set.filter(
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
            ).count(),
            "contributors": translation.change_set.filter(
                timestamp__date__gte=datetime.date.today() - datetime.timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        self.create_metrics(
            data,
            translation.stats,
            BASIC_KEYS,
            Metric.SCOPE_TRANSLATION,
            translation.pk,
        )
        return data

    def collect_user(self, user: User):
        data = user.change_set.filter(
            timestamp__date=datetime.date.today() - datetime.timedelta(days=1)
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
        self.create_metrics(data, None, None, Metric.SCOPE_USER, user.pk)
        return data

    def collect_language(self, language: Language):
        changes = Change.objects.filter(translation__language=language)
        data = {
            "changes": changes.filter(
                timestamp__date=datetime.date.today() - datetime.timedelta(days=1),
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=datetime.date.today()
                - datetime.timedelta(days=30),
            )
            .values("user")
            .distinct()
            .count(),
        }
        self.create_metrics(
            data,
            language.stats,
            SOURCE_KEYS,
            Metric.SCOPE_LANGUAGE,
            language.pk,
        )
        return data


class Metric(models.Model):
    SCOPE_GLOBAL = 0
    SCOPE_PROJECT = 1
    SCOPE_COMPONENT = 2
    SCOPE_TRANSLATION = 3
    SCOPE_USER = 4
    SCOPE_COMPONENT_LIST = 5
    SCOPE_PROJECT_LANGUAGE = 6
    SCOPE_LANGUAGE = 7

    date = models.DateField(default=datetime.date.today)
    scope = models.SmallIntegerField()
    relation = models.IntegerField()
    secondary = models.IntegerField(default=0)
    kind = models.SmallIntegerField()
    value = models.IntegerField()

    objects = MetricsManager.from_queryset(MetricQuerySet)()

    class Meta:
        unique_together = (("date", "scope", "relation", "secondary", "kind"),)
        verbose_name = "Metric"
        verbose_name_plural = "Metrics"

    def __str__(self):
        return (
            f"<{self.scope}.{self.relation}>:{self.date}:{self.get_name()}={self.value}"
        )

    def get_name(self):
        return METRIC_NAMES[self.kind]


@receiver(post_save, sender=Project)
@disable_for_loaddata
def create_metrics_project(sender, instance, created=False, **kwargs):
    if created:
        Metric.objects.initialize_metrics(
            scope=Metric.SCOPE_PROJECT, relation=instance.pk
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
