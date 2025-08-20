# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Wrapper around django.contrib.messages to work with Django REST Framework.

It also ignories messages without request object (for example from CLI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.messages import add_message as django_add_message
from django.contrib.messages import constants
from django.http import HttpRequest

if TYPE_CHECKING:
    from weblate.auth.models import HttpRequest


def get_request(request: HttpRequest):
    """Return Django request object even for DRF requests."""
    return getattr(request, "_request", request)


def add_message(
    request: HttpRequest | None,
    level: int,
    message: str,
    extra_tags: str = "",
) -> None:
    if request is not None:
        django_add_message(
            get_request(request),
            level,
            message,
            extra_tags=extra_tags,
            fail_silently=True,
        )


def debug(
    request: HttpRequest | None,
    message: str,
    extra_tags: str = "",
) -> None:
    """Add a message with the ``DEBUG`` level."""
    add_message(request, constants.DEBUG, message, extra_tags)


def info(
    request: HttpRequest | None,
    message: str,
    extra_tags: str = "",
) -> None:
    """Add a message with the ``INFO`` level."""
    add_message(request, constants.INFO, message, extra_tags)


def success(
    request: HttpRequest | None,
    message: str,
    extra_tags: str = "",
) -> None:
    """Add a message with the ``SUCCESS`` level."""
    add_message(request, constants.SUCCESS, message, extra_tags)


def warning(
    request: HttpRequest | None,
    message: str,
    extra_tags: str = "",
) -> None:
    """Add a message with the ``WARNING`` level."""
    add_message(request, constants.WARNING, message, extra_tags)


def error(
    request: HttpRequest | None,
    message: str,
    extra_tags: str = "",
) -> None:
    """Add a message with the ``ERROR`` level."""
    add_message(request, constants.ERROR, message, extra_tags)


def get_message_kind(tags):
    if "error" in tags:
        return "danger"
    for tag in ["info", "success", "warning", "danger"]:
        if tag in tags:
            return tag
    return "info"
