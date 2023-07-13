# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps


def disable_for_loaddata(signal_handler):
    """Decorator that turns off signal handlers when loading fixture data."""

    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        if kwargs.get("raw"):
            return
        signal_handler(*args, **kwargs)

    return wrapper
