# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps


def disable_for_loaddata(signal_handler):
    """Turn off signal handlers when loading fixture data."""

    @wraps(signal_handler)
    def wrapper(*args, **kwargs) -> None:
        if kwargs.get("raw"):
            return
        signal_handler(*args, **kwargs)

    return wrapper
