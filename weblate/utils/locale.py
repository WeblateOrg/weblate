# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from contextlib import contextmanager
from locale import LC_ALL, Error, getlocale, setlocale


@contextmanager
def c_locale():
    """Context to execute something in C locale."""
    # List of locales to reset
    locales = [("C", "UTF-8"), ("en_US", "UTF-8"), ""]
    try:
        # If locale is set, insert it to the top
        currlocale = getlocale()
        if currlocale[0]:
            locales.insert(0, currlocale)
    except Error:
        pass
    # Set C locale for the execution
    setlocale(LC_ALL, "C")
    try:
        # Here the context gets executed
        yield
    finally:
        for currlocale in locales:
            try:
                setlocale(LC_ALL, currlocale)
            except Error:
                continue
            # If getlocale returns None, the locale is most
            # likely not working properly
            if getlocale()[0]:
                break
