# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django import template

from weblate.accounts.models import Subscription
from weblate.accounts.notifications import NotificationFrequency, NotificationScope

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component

register = template.Library()


@register.simple_tag
def component_lock_unsubscribe_url(user: User, component: Component) -> str:
    if not user.is_authenticated:
        return ""

    subscription = (
        Subscription.objects.filter(
            user=user,
            notification="LockNotification",
            scope=NotificationScope.SCOPE_COMPONENT,
            project_id=component.project_id,
            component_id=component.pk,
            onetime=True,
        )
        .exclude(frequency=NotificationFrequency.FREQ_NONE)
        .first()
    )
    if subscription is None:
        return ""

    return subscription.get_unsubscribe_url()
