# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data files helpers."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings


def data_dir(component, *args):
    """Return path to data dir for given component."""
    # TODO: remove once all users are migrated to data_path
    if component == "cache" and settings.CACHE_DIR:
        return os.path.join(settings.CACHE_DIR, *args)
    return os.path.join(settings.DATA_DIR, component, *args)


def data_path(component: str) -> Path:
    """Return path to data dir for given component."""
    if component == "cache" and settings.CACHE_DIR:
        # Honor cache directory if configured, legacy setups have it
        # as a subdirectory of the data directory.
        return Path(settings.CACHE_DIR)
    return Path(settings.DATA_DIR) / component
