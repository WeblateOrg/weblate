# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

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

    @wraps(view)
    def wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
        check_management_access(request)
        return view(request, *args, **kwargs)

    return wrapper


def management_permission_required(permission: str):
    """Check management access and a specific site-wide permission."""

    def decorator(view: Callable):
        @wraps(view)
        def wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
            check_management_access(request, permission)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
