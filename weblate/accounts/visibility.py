# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Installation policies for discovering users and accessing their profiles."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Q
from django.http import Http404
from django.utils.cache import add_never_cache_headers

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.contrib.auth.models import AnonymousUser
    from django.http.response import HttpResponseBase

    from weblate.auth.models import User


def can_manage_users(user: User | AnonymousUser) -> bool:
    return bool(user.has_perm("user.view") or user.has_perm("user.edit"))


def can_browse_users(user: User | AnonymousUser) -> bool:
    return settings.USER_DIRECTORY_VISIBILITY == "all" or can_manage_users(user)


def can_search_scoped_users(user: User | AnonymousUser) -> bool:
    return settings.USER_DIRECTORY_VISIBILITY in {"all", "scoped"} or can_manage_users(
        user
    )


def can_view_profile(viewer: User | AnonymousUser, target: User) -> bool:
    if settings.USER_PROFILE_VISIBILITY == "public" or viewer.pk == target.pk:
        return True
    if settings.USER_PROFILE_VISIBILITY == "authenticated" and viewer.is_authenticated:
        return True
    return can_manage_users(viewer)


def check_profile_access(viewer: User | AnonymousUser, target: User) -> None:
    if not can_view_profile(viewer, target):
        raise Http404


def profile_response[**P, R: HttpResponseBase](view: Callable[P, R]) -> Callable[P, R]:
    """Do not cache profile responses across viewers under restricted policy."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        response = view(*args, **kwargs)
        if settings.USER_PROFILE_VISIBILITY != "public":
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
