# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def management_access(view):
    """Check management access decorator."""

    @wraps(view)
    def wrapper(request: AuthenticatedHttpRequest, *args, **kwargs):
        if not request.user.has_perm("management.use"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
