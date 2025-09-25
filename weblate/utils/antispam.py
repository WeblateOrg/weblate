# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def is_spam(request: HttpRequest, texts: str | list[str]) -> bool:
    """Check whether text is considered spam."""
    # Akismet integration has been removed
    return False


def report_spam(text, user_ip, user_agent) -> None:
    """Report spam to external service."""
    # Akismet integration has been removed
    pass
