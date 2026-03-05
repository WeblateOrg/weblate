# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_not_required


def disable_for_loaddata(signal_handler):
    """Turn off signal handlers when loading fixture data."""

    @wraps(signal_handler)
    def wrapper(*args, **kwargs) -> None:
        if kwargs.get("raw"):
            return
        signal_handler(*args, **kwargs)

    return wrapper


def engage_login_not_required(view_func):
    """Apply @login_not_required only if engage page should be public."""
    # 1. Evaluate your complex condition
    if settings.REQUIRE_LOGIN and settings.PUBLIC_ENGAGE:
        return login_not_required(view_func)

    # 3. Otherwise, return the original function as-is
    return view_func
