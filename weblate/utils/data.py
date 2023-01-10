# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data files helpers."""
import os

from django.conf import settings


def data_dir(component, *args):
    """Return path to data dir for given component."""
    return os.path.join(settings.DATA_DIR, component, *args)
