# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Wrapper around django.contrib.messages to work with Django REST Framework.

It also ignories messages without request object (for example from CLI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.messages import add_message, constants

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def get_request(request: AuthenticatedHttpRequest):
    """Return Django request object even for DRF requests."""
    return getattr(request, "_request", request)


def debug(
    request: AuthenticatedHttpRequest | None,
    message: str,
    extra_tags: str = "",
    fail_silently=False,
) -> None:
    """Add a message with the ``DEBUG`` level."""
    if request is not None:
        add_message(
            get_request(request),
            constants.DEBUG,
            message,
            extra_tags=extra_tags,
            fail_silently=fail_silently,
        )


def info(
    request: AuthenticatedHttpRequest | None,
    message: str,
    extra_tags: str = "",
    fail_silently=False,
) -> None:
    """Add a message with the ``INFO`` level."""
    if request is not None:
        add_message(
            get_request(request),
            constants.INFO,
            message,
            extra_tags=extra_tags,
            fail_silently=fail_silently,
        )


def success(
    request: AuthenticatedHttpRequest | None,
    message: str,
    extra_tags: str = "",
    fail_silently=False,
) -> None:
    """Add a message with the ``SUCCESS`` level."""
    if request is not None:
        add_message(
            get_request(request),
            constants.SUCCESS,
            message,
            extra_tags=extra_tags,
            fail_silently=fail_silently,
        )


def warning(
    request: AuthenticatedHttpRequest | None,
    message: str,
    extra_tags: str = "",
    fail_silently=False,
) -> None:
    """Add a message with the ``WARNING`` level."""
    if request is not None:
        add_message(
            get_request(request),
            constants.WARNING,
            message,
            extra_tags=extra_tags,
            fail_silently=fail_silently,
        )


def error(
    request: AuthenticatedHttpRequest | None,
    message: str,
    extra_tags: str = "",
    fail_silently=False,
) -> None:
    """Add a message with the ``ERROR`` level."""
    if request is not None:
        add_message(
            get_request(request),
            constants.ERROR,
            message,
            extra_tags=extra_tags,
            fail_silently=fail_silently,
        )


def get_message_kind(tags):
    if "error" in tags:
        return "danger"
    for tag in ["info", "success", "warning", "danger"]:
        if tag in tags:
            return tag
    return "info"
