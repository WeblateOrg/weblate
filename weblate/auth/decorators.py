# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps

from django.core.exceptions import PermissionDenied


def management_access(view):
    """Decorator that checks management access."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_perm("management.use"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
