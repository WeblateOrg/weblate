#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from datetime import date, timedelta
from typing import Dict, Optional, Set

from celery.schedules import crontab
from django.core.cache import cache
from django.db.models import Count, Q

from weblate.auth.models import User
from weblate.memory.models import Memory
from weblate.metrics.models import Metric
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Change, Component, ComponentList, Project, Translation
from weblate.utils.celery import app
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


def create_metrics(
    data: Dict,
    stats: Optional[Dict],
    keys: Set,
    scope: int,
    relation: int,
    secondary: int = 0,
):
    if stats is not None:
        for key in keys:
            data[key] = getattr(stats, key)

    Metric.objects.bulk_create(
        [
            Metric(
                scope=scope,
                relation=relation,
                secondary=secondary,
                name=name,
                value=value,
            )
            for name, value in data.items()
        ]
    )


def collect_global():
    stats = GlobalStats()
    data = {
        "projects": Project.objects.count(),
        "components": Component.objects.count(),
        "translations": Translation.objects.count(),
        "memory": Memory.objects.count(),
        "screenshots": Screenshot.objects.count(),
        "changes": Change.objects.filter(
            timestamp__date=date.today() - timedelta(days=1)
        ).count(),
        "contributors": Change.objects.filter(
            timestamp__date__gte=date.today() - timedelta(days=30)
        )
        .values("user")
        .distinct()
        .count(),
        "users": User.objects.count(),
    }
    create_metrics(data, stats, SOURCE_KEYS, Metric.SCOPE_GLOBAL, 0)


def collect_projects():
    for project in prefetch_stats(Project.objects.all()):
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
                timestamp__date=date.today() - timedelta(days=1)
            ).count(),
            "contributors": project.change_set.filter(
                timestamp__date__gte=date.today() - timedelta(days=30)
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

        create_metrics(
            data, project.stats, SOURCE_KEYS, Metric.SCOPE_PROJECT, project.pk
        )
        languages = prefetch_stats(
            [ProjectLanguage(project, language) for language in project.languages]
        )
        for project_language in languages:
            data = {
                "changes": project.change_set.filter(
                    translation__language=project_language.language,
                    timestamp__date=date.today() - timedelta(days=1),
                ).count(),
                "contributors": project.change_set.filter(
                    translation__language=project_language.language,
                    timestamp__date__gte=date.today() - timedelta(days=30),
                )
                .values("user")
                .distinct()
                .count(),
            }

            create_metrics(
                data,
                project.stats,
                SOURCE_KEYS,
                Metric.SCOPE_PROJECT_LANGUAGE,
                project.pk,
                project_language.language.pk,
            )


def collect_components():
    for component in prefetch_stats(Component.objects.all()):
        data = {
            "translations": component.translation_set.count(),
            "screenshots": Screenshot.objects.filter(
                translation__component=component
            ).count(),
            "changes": component.change_set.filter(
                timestamp__date=date.today() - timedelta(days=1)
            ).count(),
            "contributors": component.change_set.filter(
                timestamp__date__gte=date.today() - timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        create_metrics(
            data, component.stats, SOURCE_KEYS, Metric.SCOPE_COMPONENT, component.pk
        )


def collect_component_lists():
    for clist in prefetch_stats(ComponentList.objects.all()):
        changes = Change.objects.filter(component__in=clist.components.all())
        data = {
            "changes": changes.filter(
                timestamp__date=date.today() - timedelta(days=1)
            ).count(),
            "contributors": changes.filter(
                timestamp__date__gte=date.today() - timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        create_metrics(
            data,
            clist.stats,
            SOURCE_KEYS,
            Metric.SCOPE_COMPONENT_LIST,
            clist.pk,
        )


def collect_translations():
    for translation in prefetch_stats(Translation.objects.all()):
        data = {
            "screenshots": translation.screenshot_set.count(),
            "changes": translation.change_set.filter(
                timestamp__date=date.today() - timedelta(days=1)
            ).count(),
            "contributors": translation.change_set.filter(
                timestamp__date__gte=date.today() - timedelta(days=30)
            )
            .values("user")
            .distinct()
            .count(),
        }
        create_metrics(
            data,
            translation.stats,
            BASIC_KEYS,
            Metric.SCOPE_TRANSLATION,
            translation.pk,
        )


def collect_users():
    for user in User.objects.filter(is_active=True):
        data = user.change_set.filter(
            timestamp__date=date.today() - timedelta(days=1)
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
        create_metrics(data, None, None, Metric.SCOPE_USER, user.pk)


@app.task(trail=False)
def collect_metrics():
    collect_global()
    collect_projects()
    collect_components()
    collect_component_lists()
    collect_translations()
    collect_users()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
