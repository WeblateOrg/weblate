# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import F, Sum

from weblate.accounts.visibility import (
    can_browse_users,
    can_search_scoped_users,
    contributor_translations,
)
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.models import ContributorCount
from weblate.trans.models import Category, Component, Project, Translation
from weblate.utils.stats import CategoryLanguage, ProjectLanguage, WorkspaceLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

CONTRIBUTOR_SCOPES = (
    Project,
    ProjectLanguage,
    Category,
    CategoryLanguage,
    Component,
    Translation,
    Language,
    Workspace,
    WorkspaceLanguage,
)
type ContributorScope = (
    Project
    | ProjectLanguage
    | Category
    | CategoryLanguage
    | Component
    | Translation
    | Language
    | Workspace
    | WorkspaceLanguage
)


def can_view_contributor_ranking(viewer: User, scope: ContributorScope) -> bool:
    if not viewer.is_authenticated:
        return False
    if isinstance(scope, Language):
        return can_browse_users(viewer)
    return can_search_scoped_users(viewer)


def scoped_contributor_counts(
    viewer: User, scope: ContributorScope
) -> QuerySet[ContributorCount]:
    translations = contributor_translations(viewer)
    match scope:
        case Translation():
            translations = translations.filter(pk=scope.pk)
        case Component():
            translations = translations.filter(component=scope)
        case Category() | CategoryLanguage():
            category = scope.category if isinstance(scope, CategoryLanguage) else scope
            translations = translations.filter(
                component_id__in=category.get_component_ids_with_links()
            )
            if isinstance(scope, CategoryLanguage):
                translations = translations.filter(language=scope.language)
        case Project() | ProjectLanguage():
            project = scope.project if isinstance(scope, ProjectLanguage) else scope
            translations = translations.filter(component__in=project.child_components)
            if isinstance(scope, ProjectLanguage):
                translations = translations.filter(language=scope.language)
        case Language():
            translations = translations.filter(language=scope)
        case Workspace():
            translations = translations.for_workspace(scope)
        case WorkspaceLanguage():
            translations = translations.for_workspace(scope.workspace).filter(
                language=scope.language
            )
        case _:
            msg = f"Unsupported contributor scope: {scope!r}"
            raise TypeError(msg)

    return ContributorCount.objects.filter(
        translation_id__in=translations.values("pk"),
        user__in=User.objects.filter(is_active=True).filter_search_access(viewer),
        contributions__gt=0,
    )


def contributor_ranking(
    viewer: User, scope: ContributorScope, *, top_only: bool = False
) -> QuerySet[ContributorCount, tuple[int, int]]:
    counts = scoped_contributor_counts(viewer, scope)
    if top_only:
        counts = counts.filter(edits__gt=0)
    ranking = counts.values("user_id")
    if isinstance(scope, Translation):
        ranking = ranking.annotate(edit_count=F("edits"))
    else:
        ranking = ranking.annotate(edit_count=Sum("edits"))
    return ranking.order_by("-edit_count", "user_id").values_list(
        "user_id", "edit_count"
    )


@dataclass(frozen=True)
class RankedContributor:
    user: User
    translated: int
    translated_width: int


def load_ranked_contributors(
    rows: Iterable[tuple[int, int]],
) -> list[RankedContributor]:
    rows = list(rows)
    users = User.objects.in_bulk(user_id for user_id, _edits in rows)
    highest = rows[0][1] if rows else 0
    return [
        RankedContributor(
            users[user_id], edits, 100 * edits // highest if highest else 0
        )
        for user_id, edits in rows
        if user_id in users
    ]
