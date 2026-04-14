# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from weblate.auth.models import User


class NotificationFrequency(IntegerChoices):
    FREQ_NONE = 0, gettext_lazy("No notification")
    FREQ_INSTANT = 1, gettext_lazy("Instant notification")
    FREQ_DAILY = 2, gettext_lazy("Daily digest")
    FREQ_WEEKLY = 3, gettext_lazy("Weekly digest")
    FREQ_MONTHLY = 4, gettext_lazy("Monthly digest")


class NotificationScope(IntegerChoices):
    SCOPE_ALL = 0, "All"
    SCOPE_WATCHED = 10, "Watched"
    SCOPE_ADMIN = 20, "Administered"
    SCOPE_PROJECT = 30, "Project"
    SCOPE_COMPONENT = 40, "Component"


def create_default_notifications(user: User) -> None:
    for scope, frequency, notification in settings.DEFAULT_NOTIFICATIONS:
        user.subscription_set.get_or_create(
            scope=scope, notification=notification, defaults={"frequency": frequency}
        )
