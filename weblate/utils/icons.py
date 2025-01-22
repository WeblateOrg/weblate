# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import lru_cache

from django.contrib.staticfiles import finders


@lru_cache(maxsize=512)
def find_static_file(name: str) -> str:
    """Return cached static file finder result."""
    filename = finders.find(name)
    if not filename:
        error = f"Could not load find static file: {name}"
        raise ValueError(error)
    return filename


@lru_cache(maxsize=1024)
def load_icon(name: str, *, auto_prefix: bool = True) -> bytes:
    """Load an icon from static files."""
    if not name:
        msg = "Empty icon name"
        raise ValueError(msg)

    if auto_prefix and "/" not in name:
        name = f"icons/{name}"

    filename = find_static_file(name)

    with open(filename, "rb") as handle:
        return handle.read()
