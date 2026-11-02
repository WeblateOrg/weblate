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

    from django.contrib.auth.models import AnonymousUser
    from django.http import HttpRequest
    from django.http.response import HttpResponseBase

    from weblate.auth.models import User


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
