# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from statistics import mean, median
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, Change, Component, Project
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet

    from weblate.auth.models import User


TRANSLATOR_ACTIONS = (
    ActionEvents.CHANGE,
    ActionEvents.NEW,
    ActionEvents.ACCEPT,
)


def percentile(values: list[int], percent: int) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def summarize_metric(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": median(ordered),
        "average": mean(ordered),
        "p75": percentile(ordered, 75),
        "p90": percentile(ordered, 90),
    }


def get_translator_work_queryset(
    *,
    scope: Workspace | Project | Category | Component | None = None,
    language: str = "",
    user: User | None = None,
    access_user: User | None = None,
) -> QuerySet[Change]:
    queryset = Change.objects.filter(
        action__in=TRANSLATOR_ACTIONS,
        unit__isnull=False,
        author__isnull=False,
        author__is_active=True,
        author__is_bot=False,
    )
    if isinstance(scope, Workspace):
        queryset = queryset.filter(project__workspace=scope)
    elif isinstance(scope, Project):
        queryset = queryset.filter(project=scope)
    elif isinstance(scope, Category):
        queryset = queryset.for_category(scope)
    elif isinstance(scope, Component):
        queryset = queryset.filter(component=scope)
    if language:
        queryset = queryset.filter(language__code=language)
    if user is not None:
        queryset = queryset.filter(author=user)
    if access_user is not None:
        queryset = queryset.filter(
            component__in=Component.objects.filter_access(access_user)
        )
    return queryset


def analyze_translator_work(
    *,
    since: datetime,
    until: datetime,
    scope: Workspace | Project | Category | Component | None = None,
    language: str = "",
    user: User | None = None,
    access_user: User | None = None,
    min_changes: int = 5,
    max_changes: int = 1000,
    max_words: int = 10000,
    queryset: QuerySet[Change] | None = None,
) -> dict[str, Any]:
    if queryset is None:
        queryset = get_translator_work_queryset(
            scope=scope,
            language=language,
            user=user,
            access_user=access_user,
        )
    rows = list(
        queryset.filter(timestamp__gte=since, timestamp__lt=until)
        .annotate(day=TruncDate("timestamp"))
        .values("day", "author_id", "author__username")
        .annotate(strings=Count("id"), words=Sum("unit__num_words"))
        .order_by("day", "author__username")
    )
    included = [
        row
        for row in rows
        if min_changes <= row["strings"] <= max_changes
        and (row["words"] or 0) <= max_words
    ]
    result: dict[str, Any] = {
        "period": {"start": since.isoformat(), "end": until.isoformat()},
        "filters": {
            "language": language,
            "min_changes": min_changes,
            "max_changes": max_changes,
            "max_words": max_words,
            "actions": [action.name.lower() for action in TRANSLATOR_ACTIONS],
        },
        "user_days": {"included": len(included), "excluded": len(rows) - len(included)},
        "metrics": {},
    }
    if included:
        result["metrics"] = {
            "strings": summarize_metric([row["strings"] for row in included]),
            "words": summarize_metric([row["words"] or 0 for row in included]),
        }
    return result
