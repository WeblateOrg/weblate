# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers for initializing Weblate application servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.urls import URLPattern, URLResolver


def preload_url_patterns() -> list[URLPattern | URLResolver]:
    """
    Ensure Django URL resolver is loaded.

    Besides making URL configuration errors fail at startup, this keeps modules
    which require the main interpreter thread from being imported by an ASGI
    request adapter.
    """
    from django.conf import settings  # ruff: ignore[import-outside-top-level, unsorted-imports]
    from django.urls import get_resolver  # ruff: ignore[import-outside-top-level]

    return get_resolver(settings.ROOT_URLCONF).url_patterns
