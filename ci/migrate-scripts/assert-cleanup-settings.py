# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for cleanup settings migration."""

from weblate.addons.events import AddonEvent
from weblate.addons.models import Addon, Event

comments = Addon.objects.get(
    component__isnull=True,
    category__isnull=True,
    project__isnull=True,
    name="weblate.removal.comments",
)
assert comments.configuration == {"age": 15}
assert Event.objects.filter(addon=comments, event=AddonEvent.EVENT_DAILY).exists()
assert (
    Addon.objects.filter(
        component__isnull=True,
        category__isnull=True,
        project__isnull=True,
        name="weblate.removal.comments",
    ).count()
    == 1
)

suggestions = Addon.objects.get(
    component__isnull=True,
    category__isnull=True,
    project__isnull=True,
    name="weblate.removal.suggestions",
)
assert suggestions.configuration == {"age": 20, "votes": None}
assert Event.objects.filter(addon=suggestions, event=AddonEvent.EVENT_DAILY).exists()
