# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.accounts.notifications import (
    FREQ_INSTANT,
    FREQ_WEEKLY,
    SCOPE_ADMIN,
    SCOPE_ALL,
    SCOPE_WATCHED,
)

if TYPE_CHECKING:
    from weblate.auth.models import User

DEFAULT_NOTIFICATIONS = [
    (SCOPE_ALL, FREQ_INSTANT, "MentionCommentNotificaton"),
    (SCOPE_WATCHED, FREQ_INSTANT, "LastAuthorCommentNotificaton"),
    (SCOPE_WATCHED, FREQ_INSTANT, "MentionCommentNotificaton"),
    (SCOPE_WATCHED, FREQ_INSTANT, "NewAnnouncementNotificaton"),
    (SCOPE_WATCHED, FREQ_WEEKLY, "NewStringNotificaton"),
    (SCOPE_ADMIN, FREQ_INSTANT, "MergeFailureNotification"),
    (SCOPE_ADMIN, FREQ_INSTANT, "ParseErrorNotification"),
    (SCOPE_ADMIN, FREQ_INSTANT, "NewTranslationNotificaton"),
    (SCOPE_ADMIN, FREQ_INSTANT, "NewAlertNotificaton"),
    (SCOPE_ADMIN, FREQ_INSTANT, "NewAnnouncementNotificaton"),
]


def create_default_notifications(user: User) -> None:
    for scope, frequency, notification in DEFAULT_NOTIFICATIONS:
        user.subscription_set.get_or_create(
            scope=scope, notification=notification, defaults={"frequency": frequency}
        )
