# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data files helpers."""

import os

from django.conf import settings


def data_dir(component, *args):
    """Return path to data dir for given component."""
    if component == "cache" and settings.CACHE_DIR:
        return os.path.join(settings.CACHE_DIR, *args)
    return os.path.join(settings.DATA_DIR, component, *args)
