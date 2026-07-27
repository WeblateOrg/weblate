# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.auth.models import AuthenticatedHttpRequest


def check_management_access(
    request: AuthenticatedHttpRequest, permission: str | None = None
) -> None:
    """Check management interface access and optional site-wide permission."""
    if not request.user.has_perm("management.use"):
        raise PermissionDenied
    if permission is not None and not request.user.has_perm(permission):
        raise PermissionDenied


def management_access(view: Callable):
    """Check management access decorator."""
    if iscoroutinefunction(view):

        @wraps(view)
        async def async_wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
            await sync_to_async(check_management_access, thread_sensitive=True)(request)
            return await view(request, *args, **kwargs)

        return async_wrapper

    @wraps(view)
    def sync_wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
        check_management_access(request)
        return view(request, *args, **kwargs)

    return sync_wrapper


def management_permission_required(permission: str):
    """Check management access and a specific site-wide permission."""

    def decorator(view: Callable):
        if iscoroutinefunction(view):

            @wraps(view)
            async def async_wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
                await sync_to_async(check_management_access, thread_sensitive=True)(
                    request, permission
                )
                return await view(request, *args, **kwargs)

            return async_wrapper

        @wraps(view)
        def sync_wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
            check_management_access(request, permission)
            return view(request, *args, **kwargs)

        return sync_wrapper

    return decorator
