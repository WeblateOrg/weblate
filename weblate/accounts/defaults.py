# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.accounts.data import (
    NotificationFrequency,
    NotificationScope,
)

DEFAULT_ENABLE_AVATARS = True
DEFAULT_AVATAR_URL_PREFIX = "https://www.gravatar.com/"
DEFAULT_AVATAR_DEFAULT_IMAGE = "identicon"

DEFAULT_REGISTRATION_OPEN = True
DEFAULT_REGISTRATION_ALLOW_BACKENDS: tuple[str, ...] = ()
DEFAULT_REGISTRATION_REBIND = False
DEFAULT_REGISTRATION_EMAIL_MATCH = ".*"
DEFAULT_REGISTRATION_ALLOW_DISPOSABLE_EMAILS = False
DEFAULT_REGISTRATION_CAPTCHA = True
DEFAULT_REGISTRATION_HINTS: dict[str, str] = {}

DEFAULT_ALTCHA_COST = 3
DEFAULT_ALTCHA_MEMORY_COST = 32_768
DEFAULT_ALTCHA_PARALLELISM = 1

DEFAULT_AUDITLOG_EXPIRY = 180
DEFAULT_SUPPORT_STATUS_CHECK = True
DEFAULT_AUTO_WATCH = True
DEFAULT_CONTACT_FORM = "reply-to"

DEFAULT_PRIVATE_COMMIT_EMAIL_TEMPLATE = "{username}@users.noreply.{site_domain}"
DEFAULT_PRIVATE_COMMIT_EMAIL_OPT_IN = True
DEFAULT_PRIVATE_COMMIT_NAME_TEMPLATE = "{site_title} user {user_id}"
DEFAULT_PRIVATE_COMMIT_NAME_OPT_IN = True

DEFAULT_SOCIAL_AUTH_AUTH0_IMAGE = "auth0.svg"
DEFAULT_SOCIAL_AUTH_AUTH0_TITLE = "Auth0"
DEFAULT_SOCIAL_AUTH_SAML_IMAGE = "saml.svg"
DEFAULT_SOCIAL_AUTH_SAML_TITLE = "SAML"

DEFAULT_PASSWORD_RESET_URL = None
DEFAULT_MAXIMAL_PASSWORD_LENGTH = 72

DEFAULT_RATELIMIT_NOTIFICATION_LIMITS: tuple[tuple[int, int], ...] = (
    (3, 120),
    (10, 3_600),
    (50, 86_400),
)

DEFAULT_NOTIFICATIONS: list[tuple[int, int, str]] = [
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
        "TranslationActivitySummaryNotification",
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
