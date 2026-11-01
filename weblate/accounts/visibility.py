# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Permissions for discovering users and accessing their profiles."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache, wraps
from typing import TYPE_CHECKING, cast

from django.core.handlers.exception import response_for_exception
from django.db.models import Q
from django.http import Http404
from django.utils.cache import add_never_cache_headers

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Any

    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Model, QuerySet
    from django.http import HttpRequest
    from django.http.response import HttpResponseBase

    from weblate.auth.models import User
    from weblate.auth.permissions import PermissionObject
    from weblate.trans.models import Change


_public_viewer: ContextVar[Callable[[], User] | None] = ContextVar(
    "public_profile_viewer", default=None
)


@contextmanager
def public_profile_render() -> Generator[None, None, None]:
    """Share public permissions within a render, never across renders."""
    if _public_viewer.get() is not None:
        yield
        return
    # Models are unavailable while the accounts app imports this module.
    from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

    # Resolve lazily so rendering text without profile links needs no user query.
    token = _public_viewer.set(cache(get_anonymous))
    try:
        yield
    finally:
        _public_viewer.reset(token)


def can_manage_users(user: User | AnonymousUser) -> bool:
    return bool(user.has_perm("user.view") or user.has_perm("user.edit"))


def can_browse_users(user: User | AnonymousUser) -> bool:
    return bool(user.has_perm("user.browse") or can_manage_users(user))


def can_search_scoped_users(user: User | AnonymousUser) -> bool:
    return bool(user.has_perm("user.search") or can_browse_users(user))


def can_view_profile(viewer: User | AnonymousUser | None, target: User) -> bool:
    # Output without a request (feeds and email) follows public access.
    if viewer is None or viewer.pk is None:
        # Models are unavailable when the accounts app imports this module.
        from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

        get_public_viewer = _public_viewer.get() or get_anonymous
        viewer = get_public_viewer()
    return bool(
        viewer.pk == target.pk
        or viewer.has_perm("user.profile")
        or can_manage_users(viewer)
    )


def check_profile_access(viewer: User | AnonymousUser, target: User) -> None:
    if not can_view_profile(viewer, target):
        raise Http404


def profile_response[**P, R: HttpResponseBase](view: Callable[P, R]) -> Callable[P, R]:
    """Do not cache permission-dependent responses across viewers."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            response = view(*args, **kwargs)
        except Http404 as error:
            # Render through the normal error handler, then protect denials too.
            request = cast("HttpRequest", args[0])
            response = cast("R", response_for_exception(request, error))
        add_never_cache_headers(response)
        return response

    return wrapper


def is_resource_bounded(query: Q) -> bool:
    """
    Require a positive contributor scope in every matching Boolean branch.

    Inspect the parsed predicates, never the query text: merely mentioning a
    scope in a negation or one side of an OR does not bound the result set.
    Only contributes predicates produce these exact resource lookups.
    """
    if query.negated or not query.children:
        return False
    bounded = [
        is_resource_bounded(child)
        if isinstance(child, Q)
        else isinstance(child, tuple)
        and child[0] in {"change__project__slug__iexact", "change__component_id__in"}
        for child in query.children
    ]
    return all(bounded) if query.connector == "OR" else any(bounded)


def contribution_scope(resource: Model) -> PermissionObject | None:
    """Resolve attribution to its most specific permission scope."""
    from weblate.trans.models import Change, Comment, Suggestion, Translation  # ruff: ignore[import-outside-top-level]

    if isinstance(resource, Change):
        if resource.translation is not None:
            return resource.translation
        if resource.unit is not None:
            return resource.unit.translation
        if resource.component is not None and resource.language_id is not None:
            return Translation(
                component=resource.component, language_id=resource.language_id
            )
        if resource.project is not None and resource.language is not None:
            from weblate.utils.stats import ProjectLanguage  # ruff: ignore[import-outside-top-level]

            return ProjectLanguage(resource.project, resource.language)
        return resource.component or resource.project or resource.workspace
    if isinstance(resource, (Comment, Suggestion)):
        return resource.unit.translation
    return cast("PermissionObject", resource)


def can_view_contributor(
    viewer: User | AnonymousUser | None, resource: Model | None
) -> bool:
    """Authorize attribution independently from profile access."""
    if viewer is None or viewer.pk is None:
        from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

        viewer = (_public_viewer.get() or get_anonymous)()
    scope = contribution_scope(resource) if resource else None
    if scope is None:
        return bool(viewer.is_superuser)
    from weblate.trans.models import Translation  # ruff: ignore[import-outside-top-level]
    from weblate.utils.stats import ProjectLanguage  # ruff: ignore[import-outside-top-level]

    key: tuple[object, ...]
    if isinstance(scope, Translation):
        key = (type(scope), scope.component_id, scope.language_id)
    elif isinstance(scope, ProjectLanguage):
        key = (type(scope), scope.project.pk, scope.language.pk)
    else:
        key = (type(scope), scope.pk)
    decisions = getattr(viewer, "contributor_visibility", None)
    if decisions is None:
        decisions = viewer.contributor_visibility = {}
    if key not in decisions:
        from weblate.workspaces.models import Workspace  # ruff: ignore[import-outside-top-level]

        if isinstance(scope, Workspace):
            decisions[key] = bool(
                viewer.has_perm("workspace.edit", scope)
                or viewer.has_perm("workspace.edit_members", scope)
            )
        else:
            decisions[key] = bool(viewer.has_perm("contribution.view_author", scope))
    return decisions[key]


def public_change_details(
    change: Change, viewer: User | AnonymousUser | None
) -> dict[str, Any]:
    """Expose only known non-identifying structured history metadata."""
    if can_view_contributor(viewer, change):
        return change.details
    from weblate.trans.actions import ActionEvents  # ruff: ignore[import-outside-top-level]

    comment_actions = {
        ActionEvents.COMMENT,
        ActionEvents.COMMENT_DELETE,
        ActionEvents.COMMENT_RESOLVE,
    }
    result: dict[str, Any] = {
        key: value
        for key, value in change.details.items()
        if (key in {"count", "state", "old_state"} and isinstance(value, int))
        or (key == "language" and isinstance(value, str))
        or (
            (
                key in {"source", "target"}
                or (key == "comment" and change.action in comment_actions)
            )
            and (
                isinstance(value, str)
                or (
                    isinstance(value, list)
                    and all(isinstance(item, str) for item in value)
                )
            )
        )
    }
    for key in ("source_snapshot", "previous_source_snapshot"):
        snapshot = change.details.get(key)
        if not isinstance(snapshot, dict):
            continue
        string_fields = {
            "text",
            "language_code",
            "language_name",
            "language_direction",
            "formula",
        }
        integer_fields = {"language_id", "plural_id", "number", "plural_type"}
        if all(isinstance(snapshot.get(field), str) for field in string_fields) and all(
            type(snapshot.get(field)) is int for field in integer_fields
        ):
            result[key] = {
                field: snapshot[field] for field in string_fields | integer_fields
            }
    return result


def contributor_translation_ids(viewer: User | AnonymousUser) -> list[int]:
    """Compute authorized translation scopes once per permission cache lifetime."""
    from weblate.trans.models import Translation  # ruff: ignore[import-outside-top-level]

    if viewer.pk is None:
        from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

        viewer = get_anonymous()
    viewer = cast("User", viewer)
    if not hasattr(viewer, "contributor_translations"):
        viewer.contributor_translations = list(
            Translation.objects.filter_access(viewer)
            .filter_permission_scope(viewer, "contribution.view_author")
            .values_list("pk", flat=True)
        )
    return viewer.contributor_translations


def filter_contributor_changes[QuerySetT: QuerySet](
    queryset: QuerySetT, viewer: User, *, enabled: bool = True
) -> QuerySetT:
    """Prevent author filters from acting as attribution oracles."""
    if not enabled or viewer.is_superuser:
        return queryset
    from weblate.auth.scope import (  # ruff: ignore[import-outside-top-level]
        get_permission_scope_query,
        get_project_language_permission_query,
    )

    component_scope = get_permission_scope_query(
        viewer,
        "contribution.view_author",
        component_path="component",
        language_path="language_id",
    )
    return queryset.filter(
        Q(translation_id__in=contributor_translation_ids(viewer))
        | (Q(translation__isnull=True, component__isnull=False) & component_scope)
        | Q(
            translation__isnull=True,
            component__isnull=True,
            language__isnull=True,
            project__in=viewer.projects_with_perm("contribution.view_author"),
        )
        | (
            Q(
                translation__isnull=True,
                component__isnull=True,
                project__isnull=False,
                language__isnull=False,
            )
            & get_project_language_permission_query(viewer, "contribution.view_author")
        )
        | (
            Q(translation__isnull=True, component__isnull=True, project__isnull=True)
            & (
                Q(workspace__in=viewer.workspaces_with_perm("workspace.edit"))
                | Q(workspace__in=viewer.workspaces_with_perm("workspace.edit_members"))
            )
        )
    )
