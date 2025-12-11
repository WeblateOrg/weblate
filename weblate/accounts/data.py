# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.accounts.notifications import NotificationFrequency, NotificationScope

if TYPE_CHECKING:
    from weblate.auth.models import User

DEFAULT_NOTIFICATIONS = [
    (
        NotificationScope.SCOPE_ALL,
        NotificationFrequency.FREQ_INSTANT,
        "MentionCommentNotificaton",
    ),
    (
        NotificationScope.SCOPE_WATCHED,
        NotificationFrequency.FREQ_INSTANT,
        "LastAuthorCommentNotificaton",
    ),
    (
        NotificationScope.SCOPE_WATCHED,
        NotificationFrequency.FREQ_INSTANT,
        "MentionCommentNotificaton",
    ),
    (
        NotificationScope.SCOPE_WATCHED,
        NotificationFrequency.FREQ_INSTANT,
        "NewAnnouncementNotificaton",
    ),
    (
        NotificationScope.SCOPE_WATCHED,
        NotificationFrequency.FREQ_WEEKLY,
        "NewStringNotificaton",
    ),
    (
        NotificationScope.SCOPE_ADMIN,
        NotificationFrequency.FREQ_INSTANT,
        "MergeFailureNotification",
    ),
    (
        NotificationScope.SCOPE_ADMIN,
        NotificationFrequency.FREQ_INSTANT,
        "ParseErrorNotification",
    ),
    (
        NotificationScope.SCOPE_ADMIN,
        NotificationFrequency.FREQ_INSTANT,
        "NewTranslationNotificaton",
    ),
    (
        NotificationScope.SCOPE_ADMIN,
        NotificationFrequency.FREQ_INSTANT,
        "NewAlertNotificaton",
    ),
    (
        NotificationScope.SCOPE_ADMIN,
        NotificationFrequency.FREQ_INSTANT,
        "NewAnnouncementNotificaton",
    ),
]


def create_default_notifications(user: User) -> None:
    for scope, frequency, notification in DEFAULT_NOTIFICATIONS:
        user.subscription_set.get_or_create(
            scope=scope, notification=notification, defaults={"frequency": frequency}
        )
